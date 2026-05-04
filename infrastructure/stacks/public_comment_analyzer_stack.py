"""Main CDK stack for Public Comment Analyzer infrastructure."""

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    Tags,
    BundlingOptions,
    ILocalBundling,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_apigateway as apigateway,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_iam as iam,
    aws_certificatemanager as acm,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct
import jsii
import json
import os
import subprocess


@jsii.implements(ILocalBundling)
class _PipBundling:
    """Local bundling that installs pip dependencies without Docker."""

    def __init__(self, source_path: str):
        self._source_path = source_path

    def try_bundle(self, output_dir: str, *, image=None, **kwargs) -> bool:
        # Resolve source path relative to infrastructure/ directory
        source = os.path.join(os.path.dirname(__file__), "..", self._source_path)
        source = os.path.abspath(source)
        req_file = os.path.join(source, "requirements.txt")
        # Install pip dependencies into output directory
        if os.path.exists(req_file):
            cmd = [
                "pip", "install",
                "--target", output_dir,
                "--upgrade",
                "-r", req_file,
            ]
            # On non-Linux (e.g. macOS), cross-compile for Lambda's Linux runtime
            import platform
            if platform.system() != "Linux":
                cmd[2:2] = ["--platform", "manylinux2014_x86_64", "--only-binary=:all:"]
            subprocess.check_call(cmd)
        # Copy source files (exclude test files and copy_shared.sh)
        import shutil
        for item in os.listdir(source):
            full = os.path.join(source, item)
            dest = os.path.join(output_dir, item)
            if os.path.isfile(full) and not item.startswith('test_') and item != 'copy_shared.sh':
                shutil.copy2(full, dest)
        return True


@jsii.implements(ILocalBundling)
class _LayerBundling:
    """Local bundling for Lambda Layer that installs shared code + deps into python/ directory."""

    def __init__(self, shared_path: str):
        self._shared_path = shared_path

    def try_bundle(self, output_dir: str, *, image=None, **kwargs) -> bool:
        import shutil
        import platform

        source = os.path.join(os.path.dirname(__file__), "..", self._shared_path)
        source = os.path.abspath(source)

        # Lambda layers expect code under python/
        python_dir = os.path.join(output_dir, "python")
        os.makedirs(python_dir, exist_ok=True)

        # Install shared requirements into python/
        req_file = os.path.join(source, "requirements.txt")
        if os.path.exists(req_file):
            cmd = [
                "pip", "install",
                "--target", python_dir,
                "--upgrade",
                "-r", req_file,
            ]
            if platform.system() != "Linux":
                cmd[2:2] = ["--platform", "manylinux2014_x86_64", "--only-binary=:all:"]
            subprocess.check_call(cmd)

        # Copy shared Python modules (exclude tests)
        for item in os.listdir(source):
            if item.endswith(".py") and not item.startswith("test_"):
                shutil.copy2(os.path.join(source, item), os.path.join(python_dir, item))

        return True


class PublicCommentAnalyzerStack(Stack):
    """CDK Stack for Public Comment Analyzer."""

    def __init__(self, scope: Construct, construct_id: str, environment: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = environment
        
        # Custom domain configuration (optional)
        self.domain_name = self.node.try_get_context("domain_name")
        self.certificate_arn = self.node.try_get_context("certificate_arn")
        
        # Allowed origin for CORS — set via context or default to CloudFront domain
        # In production, override with your actual domain: cdk deploy -c allowed_origin=https://yourdomain.com
        self.allowed_origin = self.node.try_get_context("allowed_origin") or ""
        
        # Common tags for all resources
        self.common_tags = {
            "Application": "PublicCommentAnalyzer",
            "Environment": environment,
            "ManagedBy": "CDK"
        }
        
        # Apply tags to stack
        for key, value in self.common_tags.items():
            self.tags.set_tag(key, value)

        # Create S3 buckets
        self.data_bucket = self._create_data_bucket()
        self.frontend_bucket = self._create_frontend_bucket()
        
        # Create DynamoDB table
        self.jobs_table = self._create_jobs_table()
        
        # Create access password secret
        self.access_password_secret = self._create_access_password_secret()
        
        # Create IAM roles
        self.lambda_role = self._create_lambda_role()
        
        # Create shared Lambda Layer
        self.shared_layer = self._create_shared_layer()
        
        # Create Lambda functions
        self.upload_handler = self._create_upload_handler()
        self.row_processor = self._create_row_processor()
        self.aggregate_analyzer = self._create_aggregate_analyzer()
        self.dashboard_generator = self._create_dashboard_generator()
        
        # Create API Gateway
        self.api = self._create_api_gateway()
        
        # Create CloudFront distribution
        self.distribution = self._create_cloudfront_distribution()
        
        # Outputs
        self._create_outputs()

    def _create_data_bucket(self) -> s3.Bucket:
        """Create S3 bucket for data storage (uploads and results)."""
        bucket = s3.Bucket(
            self,
            "DataBucket",
            bucket_name=f"public-comment-analyzer-data-{self.env_name}-{self.account}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=False,
            removal_policy=RemovalPolicy.RETAIN,
            enforce_ssl=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldFiles",
                    enabled=True,
                    expiration=Duration.days(7)
                )
            ]
            # No CORS needed — frontend accesses data via API Gateway/presigned URLs,
            # not directly from the browser to this bucket.
        )
        
        return bucket

    def _create_frontend_bucket(self) -> s3.Bucket:
        """Create S3 bucket for static website hosting."""
        bucket = s3.Bucket(
            self,
            "FrontendBucket",
            bucket_name=f"public-comment-analyzer-frontend-{self.env_name}-{self.account}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=True,
                block_public_policy=True,
                ignore_public_acls=True,
                restrict_public_buckets=True
            ),
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN
        )
        
        return bucket

    def _create_jobs_table(self) -> dynamodb.Table:
        """Create DynamoDB table for job tracking."""
        table = dynamodb.Table(
            self,
            "JobsTable",
            table_name=f"PublicCommentAnalyzer-Jobs-{self.env_name}",
            partition_key=dynamodb.Attribute(
                name="jobId",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=True,
            time_to_live_attribute="ttl"
        )
        
        return table

    def _create_access_password_secret(self) -> secretsmanager.Secret:
        """Create Secrets Manager secret for the site access password hash.

        The secret is created with an empty hash. Auth returns 500 "Auth not
        configured" until you set it post-deploy:

            pwd='your-strong-password'
            hash=$(printf %s "$pwd" | shasum -a 256 | awk '{print $1}')
            aws secretsmanager put-secret-value \\
              --secret-id PublicCommentAnalyzer-AccessPassword-<env> \\
              --secret-string "{\\"password_hash\\":\\"$hash\\"}"
        """
        return secretsmanager.Secret(
            self,
            "AccessPasswordSecret",
            secret_name=f"PublicCommentAnalyzer-AccessPassword-{self.env_name}",
            description="Access password hash. Set via aws secretsmanager put-secret-value after first deploy.",
            secret_string_value=cdk.SecretValue.unsafe_plain_text(
                json.dumps({"password_hash": ""})
            ),
        )

    def _create_lambda_role(self) -> iam.Role:
        """Create IAM role for Lambda functions with necessary permissions."""
        role = iam.Role(
            self,
            "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Execution role for Public Comment Analyzer Lambda functions",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )
        
        # S3 access for data bucket
        self.data_bucket.grant_read_write(role)
        
        # DynamoDB access
        self.jobs_table.grant_read_write_data(role)
        
        # Lambda self-invoke permission for async processing
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["lambda:InvokeFunction"],
                resources=[
                    f"arn:aws:lambda:{self.region}:{self.account}:function:PublicCommentAnalyzer-RowProcessor-*",
                    f"arn:aws:lambda:{self.region}:{self.account}:function:PublicCommentAnalyzer-AggregateAnalyzer-*"
                ]
            )
        )
        
        # AWS Marketplace permissions for Bedrock model access (read-only)
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "aws-marketplace:ViewSubscriptions"
                ],
                resources=["*"]
            )
        )
        
        # Bedrock access — scoped to this account's region only
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream"
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.*",
                    f"arn:aws:bedrock:{self.region}::foundation-model/us.anthropic.*",
                    f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/us.anthropic.*",
                    f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/anthropic.*",
                    # Cross-region inference profiles
                    f"arn:aws:bedrock:us-*::foundation-model/anthropic.*",
                    f"arn:aws:bedrock:us-*::foundation-model/us.anthropic.*",
                    f"arn:aws:bedrock:us-*:{self.account}:inference-profile/us.anthropic.*"
                ]
            )
        )
        
        # Secrets Manager access for access password
        self.access_password_secret.grant_read(role)
        
        return role

    def _create_shared_layer(self) -> lambda_.LayerVersion:
        """Create Lambda Layer with shared modules (auth, file_parser, file_writer, dynamodb_client)."""
        layer = lambda_.LayerVersion(
            self,
            "SharedLayer",
            layer_version_name=f"PublicCommentAnalyzer-Shared-{self.env_name}",
            description="Shared modules for Public Comment Analyzer Lambda functions",
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
            code=lambda_.Code.from_asset(
                "../backend/shared",
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash", "-c",
                        "mkdir -p /asset-output/python && "
                        "pip install -r requirements.txt -t /asset-output/python && "
                        "cp *.py /asset-output/python/ 2>/dev/null; "
                        "rm -f /asset-output/python/test_*.py"
                    ],
                    local=_LayerBundling("../backend/shared"),
                ),
            ),
        )
        return layer

    def _create_upload_handler(self) -> lambda_.Function:
        """Create Lambda function for file upload handling."""
        function = lambda_.Function(
            self,
            "UploadHandler",
            function_name=f"PublicCommentAnalyzer-UploadHandler-{self.env_name}",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(
                "../backend/upload_handler",
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output"
                    ],
                    local=_PipBundling("../backend/upload_handler"),
                ),
            ),
            layers=[self.shared_layer],
            role=self.lambda_role,
            timeout=Duration.seconds(30),
            memory_size=512,
            environment={
                "DATA_BUCKET": self.data_bucket.bucket_name,
                "JOBS_TABLE": self.jobs_table.table_name,
                "ENVIRONMENT": self.env_name,
                "ALLOWED_ORIGIN": self.allowed_origin,
                "ACCESS_PASSWORD_SECRET_NAME": self.access_password_secret.secret_name
            }
        )
        
        return function

    def _create_row_processor(self) -> lambda_.Function:
        """Create Lambda function for row processing."""
        function = lambda_.Function(
            self,
            "RowProcessor",
            function_name=f"PublicCommentAnalyzer-RowProcessor-{self.env_name}",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(
                "../backend/row_processor",
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output"
                    ],
                    local=_PipBundling("../backend/row_processor"),
                ),
            ),
            layers=[self.shared_layer],
            role=self.lambda_role,
            timeout=Duration.minutes(15),
            memory_size=1024,
            reserved_concurrent_executions=500,
            environment={
                "DATA_BUCKET": self.data_bucket.bucket_name,
                "JOBS_TABLE": self.jobs_table.table_name,
                "ENVIRONMENT": self.env_name,
                "IAM_POLICY_VERSION": "3",
                "AGGREGATE_ANALYZER_FUNCTION": f"PublicCommentAnalyzer-AggregateAnalyzer-{self.env_name}",
                "ALLOWED_ORIGIN": self.allowed_origin,
                "ACCESS_PASSWORD_SECRET_NAME": self.access_password_secret.secret_name
            }
        )
        
        return function

    def _create_aggregate_analyzer(self) -> lambda_.Function:
        """Create Lambda function for aggregate analysis."""
        function = lambda_.Function(
            self,
            "AggregateAnalyzer",
            function_name=f"PublicCommentAnalyzer-AggregateAnalyzer-{self.env_name}",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(
                "../backend/aggregate_analyzer",
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output"
                    ],
                    local=_PipBundling("../backend/aggregate_analyzer"),
                ),
            ),
            layers=[self.shared_layer],
            role=self.lambda_role,
            timeout=Duration.minutes(15),
            memory_size=512,
            environment={
                "DATA_BUCKET": self.data_bucket.bucket_name,
                "JOBS_TABLE": self.jobs_table.table_name,
                "ENVIRONMENT": self.env_name,
                "ALLOWED_ORIGIN": self.allowed_origin,
                "ACCESS_PASSWORD_SECRET_NAME": self.access_password_secret.secret_name
            }
        )
        
        return function

    def _create_dashboard_generator(self) -> lambda_.Function:
        """Create Lambda function for custom dashboard generation."""
        function = lambda_.Function(
            self,
            "DashboardGenerator",
            function_name=f"PublicCommentAnalyzer-DashboardGenerator-{self.env_name}",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(
                "../backend/dashboard_generator",
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output"
                    ],
                    local=_PipBundling("../backend/dashboard_generator"),
                ),
            ),
            layers=[self.shared_layer],
            role=self.lambda_role,
            timeout=Duration.minutes(15),
            memory_size=512,
            environment={
                "DATA_BUCKET": self.data_bucket.bucket_name,
                "JOBS_TABLE": self.jobs_table.table_name,
                "ENVIRONMENT": self.env_name,
                "ALLOWED_ORIGIN": self.allowed_origin,
                "ACCESS_PASSWORD_SECRET_NAME": self.access_password_secret.secret_name
            }
        )
        
        return function

    def _create_api_gateway(self) -> apigateway.RestApi:
        """Create API Gateway with Lambda integrations."""
        api = apigateway.RestApi(
            self,
            "PublicCommentAnalyzerAPI",
            rest_api_name=f"PublicCommentAnalyzer-{self.env_name}",
            description="API for Public Comment Analyzer",
            deploy_options=apigateway.StageOptions(
                stage_name=self.env_name,
                throttling_rate_limit=100,
                throttling_burst_limit=200,
                logging_level=apigateway.MethodLoggingLevel.OFF,
                data_trace_enabled=False,
                metrics_enabled=True
            ),
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=[self.allowed_origin] if self.allowed_origin else apigateway.Cors.ALL_ORIGINS,
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["Content-Type", "Authorization", "X-Requested-With", "X-Access-Key"]
            ),
            binary_media_types=["multipart/form-data"]
        )
        
        # Define request validation models
        process_request_model = api.add_model(
            "ProcessRequestModel",
            content_type="application/json",
            model_name="ProcessRequest",
            schema=apigateway.JsonSchema(
                schema=apigateway.JsonSchemaVersion.DRAFT4,
                title="ProcessRequest",
                type=apigateway.JsonSchemaType.OBJECT,
                properties={
                    "fileId": apigateway.JsonSchema(
                        type=apigateway.JsonSchemaType.STRING,
                        description="UUID of the uploaded file"
                    ),
                    "analysisColumns": apigateway.JsonSchema(
                        type=apigateway.JsonSchemaType.ARRAY,
                        items=apigateway.JsonSchema(
                            type=apigateway.JsonSchemaType.OBJECT,
                            properties={
                                "name": apigateway.JsonSchema(
                                    type=apigateway.JsonSchemaType.STRING,
                                    min_length=1
                                ),
                                "instructions": apigateway.JsonSchema(
                                    type=apigateway.JsonSchemaType.STRING,
                                    min_length=1
                                )
                            },
                            required=["name", "instructions"]
                        ),
                        min_items=1
                    )
                },
                required=["fileId", "analysisColumns"]
            )
        )
        
        # Create request validator
        request_validator = api.add_request_validator(
            "RequestValidator",
            validate_request_body=True,
            validate_request_parameters=True
        )
        
        # /api resource
        api_resource = api.root.add_resource("api")
        
        # POST /api/upload - accepts multipart/form-data for file upload
        upload_resource = api_resource.add_resource("upload")
        upload_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(
                self.upload_handler,
                proxy=True
            ),
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                ),
                apigateway.MethodResponse(status_code="400"),
                apigateway.MethodResponse(status_code="500")
            ]
        )
        
        # POST /api/process - starts row processing job
        process_resource = api_resource.add_resource("process")
        process_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(
                self.row_processor,
                proxy=True
            ),
            request_validator=request_validator,
            request_models={
                "application/json": process_request_model
            },
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                ),
                apigateway.MethodResponse(status_code="400"),
                apigateway.MethodResponse(status_code="500")
            ]
        )

        # POST /api/process/{jobId}/preview-confirm - user confirms the preview classifications
        # are reasonable; row processor then re-runs against the full file.
        process_job_resource = process_resource.add_resource("{jobId}")
        process_preview_confirm_resource = process_job_resource.add_resource("preview-confirm")
        process_preview_confirm_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.row_processor, proxy=True),
            request_parameters={"method.request.path.jobId": True},
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                ),
                apigateway.MethodResponse(status_code="400"),
                apigateway.MethodResponse(status_code="404"),
                apigateway.MethodResponse(status_code="409"),
                apigateway.MethodResponse(status_code="500")
            ]
        )

        # GET /api/status/{jobId} - query DynamoDB for job status
        status_resource = api_resource.add_resource("status")
        status_job_resource = status_resource.add_resource("{jobId}")
        
        # Create Lambda for status checking
        status_handler = lambda_.Function(
            self,
            "StatusHandler",
            function_name=f"PublicCommentAnalyzer-StatusHandler-{self.env_name}",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("../backend/status_handler"),
            layers=[self.shared_layer],
            role=self.lambda_role,
            timeout=Duration.seconds(10),
            environment={
                "JOBS_TABLE": self.jobs_table.table_name,
                "ALLOWED_ORIGIN": self.allowed_origin,
                "ACCESS_PASSWORD_SECRET_NAME": self.access_password_secret.secret_name
            }
        )
        
        status_job_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(status_handler, proxy=True),
            request_parameters={
                "method.request.path.jobId": True
            },
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                ),
                apigateway.MethodResponse(status_code="404"),
                apigateway.MethodResponse(status_code="500")
            ]
        )
        
        # GET /api/results/{jobId} - integrate with Aggregate Analyzer Lambda
        results_resource = api_resource.add_resource("results")
        results_job_resource = results_resource.add_resource("{jobId}")
        results_job_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.aggregate_analyzer, proxy=True),
            request_parameters={
                "method.request.path.jobId": True
            },
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                ),
                apigateway.MethodResponse(status_code="400"),
                apigateway.MethodResponse(status_code="404"),
                apigateway.MethodResponse(status_code="500")
            ]
        )
        
        # POST /api/dashboard/{jobId} - generate custom dashboard charts
        dashboard_resource = api_resource.add_resource("dashboard")
        dashboard_job_resource = dashboard_resource.add_resource("{jobId}")
        dashboard_job_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.dashboard_generator, proxy=True),
            request_parameters={
                "method.request.path.jobId": True
            },
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                ),
                apigateway.MethodResponse(status_code="400"),
                apigateway.MethodResponse(status_code="404"),
                apigateway.MethodResponse(status_code="500")
            ]
        )
        
        # POST /api/auth/validate - validate access password
        auth_resource = api_resource.add_resource("auth")
        auth_validate_resource = auth_resource.add_resource("validate")
        
        auth_handler = lambda_.Function(
            self,
            "AuthHandler",
            function_name=f"PublicCommentAnalyzer-AuthHandler-{self.env_name}",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("../backend/auth_handler"),
            role=self.lambda_role,
            timeout=Duration.seconds(10),
            environment={
                "ALLOWED_ORIGIN": self.allowed_origin,
                "ACCESS_PASSWORD_SECRET_NAME": self.access_password_secret.secret_name
            }
        )
        
        auth_validate_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(auth_handler, proxy=True),
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                ),
                apigateway.MethodResponse(status_code="401"),
                apigateway.MethodResponse(status_code="500")
            ]
        )
        
        return api


    def _create_cloudfront_distribution(self) -> cloudfront.Distribution:
        """Create CloudFront distribution for frontend and API."""
        # Origin Access Identity for S3
        oai = cloudfront.OriginAccessIdentity(
            self,
            "FrontendOAI",
            comment="OAI for Public Comment Analyzer frontend"
        )
        
        self.frontend_bucket.grant_read(oai)
        
        # Security response headers policy
        security_headers = cloudfront.ResponseHeadersPolicy(
            self,
            "SecurityHeadersPolicy",
            response_headers_policy_name=f"SecurityHeaders-{self.env_name}",
            security_headers_behavior=cloudfront.ResponseSecurityHeadersBehavior(
                content_type_options=cloudfront.ResponseHeadersContentTypeOptions(
                    override=True
                ),
                frame_options=cloudfront.ResponseHeadersFrameOptions(
                    frame_option=cloudfront.HeadersFrameOption.DENY,
                    override=True
                ),
                referrer_policy=cloudfront.ResponseHeadersReferrerPolicy(
                    referrer_policy=cloudfront.HeadersReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN,
                    override=True
                ),
                strict_transport_security=cloudfront.ResponseHeadersStrictTransportSecurity(
                    access_control_max_age=Duration.days(365),
                    include_subdomains=True,
                    preload=True,
                    override=True
                ),
                xss_protection=cloudfront.ResponseHeadersXSSProtection(
                    protection=True,
                    mode_block=True,
                    override=True
                )
            )
        )
        
        # Build CloudFront distribution configuration
        distribution_config = {
            "default_behavior": cloudfront.BehaviorOptions(
                origin=origins.S3Origin(
                    self.frontend_bucket,
                    origin_access_identity=oai
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                response_headers_policy=security_headers
            ),
            "additional_behaviors": {
                "/api/*": cloudfront.BehaviorOptions(
                    origin=origins.RestApiOrigin(self.api),
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL
                )
            },
            "default_root_object": "index.html",
            "error_responses": [
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.minutes(5)
                )
            ]
        }
        
        # Add custom domain if provided
        if self.domain_name and self.certificate_arn:
            # Import the certificate
            certificate = acm.Certificate.from_certificate_arn(
                self,
                "Certificate",
                self.certificate_arn
            )
            distribution_config["domain_names"] = [self.domain_name]
            distribution_config["certificate"] = certificate
        
        distribution = cloudfront.Distribution(
            self,
            "CloudFrontDistribution",
            **distribution_config
        )
        
        return distribution

    def _create_outputs(self) -> None:
        """Create CloudFormation outputs."""
        CfnOutput(
            self,
            "DataBucketName",
            value=self.data_bucket.bucket_name,
            description="S3 bucket for data storage"
        )
        
        CfnOutput(
            self,
            "FrontendBucketName",
            value=self.frontend_bucket.bucket_name,
            description="S3 bucket for frontend hosting"
        )
        
        CfnOutput(
            self,
            "JobsTableName",
            value=self.jobs_table.table_name,
            description="DynamoDB table for job tracking"
        )
        
        CfnOutput(
            self,
            "ApiUrl",
            value=self.api.url,
            description="API Gateway URL"
        )
        
        CfnOutput(
            self,
            "CloudFrontUrl",
            value=f"https://{self.distribution.distribution_domain_name}",
            description="CloudFront distribution URL"
        )
        
        CfnOutput(
            self,
            "CloudFrontDistributionId",
            value=self.distribution.distribution_id,
            description="CloudFront distribution ID for cache invalidation"
        )
