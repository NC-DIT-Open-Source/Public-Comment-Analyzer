#!/usr/bin/env python3
"""AWS CDK application for Public Comment Analyzer."""

import aws_cdk as cdk
from stacks.public_comment_analyzer_stack import PublicCommentAnalyzerStack


app = cdk.App()

# Get environment from context or use default
environment = app.node.try_get_context("environment") or "dev"

PublicCommentAnalyzerStack(
    app,
    f"PublicCommentAnalyzerStack-{environment}",
    env=cdk.Environment(
        account=app.node.try_get_context("account"),
        region=app.node.try_get_context("region") or "us-east-1"
    ),
    environment=environment,
    description="Public Comment Analyzer - AI-powered comment analysis using AWS Bedrock"
)

app.synth()
