#!/usr/bin/env node

/**
 * Deployment script for Public Comment Analyzer frontend
 * 
 * This script:
 * 1. Reads the CloudFormation outputs to get bucket name and distribution ID
 * 2. Syncs the built Angular app to S3
 * 3. Invalidates the CloudFront cache
 * 
 * Usage:
 *   npm run deploy              # Deploy to S3 and invalidate CloudFront
 *   npm run deploy:dry-run      # Show what would be deployed without actually deploying
 */

const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// Parse command line arguments
const isDryRun = process.argv.includes('--dry-run');
const environment = process.env.ENVIRONMENT || 'dev';

console.log(`\n🚀 Deploying Public Comment Analyzer Frontend`);
console.log(`   Environment: ${environment}`);
console.log(`   Dry Run: ${isDryRun ? 'Yes' : 'No'}\n`);

// Get CDK outputs
function getCdkOutputs() {
  try {
    console.log('📋 Reading CDK outputs...');
    const cdkOutputsPath = path.join(__dirname, '../../infrastructure/cdk-outputs.json');
    
    if (!fs.existsSync(cdkOutputsPath)) {
      console.error('❌ Error: cdk-outputs.json not found.');
      console.error('   Please deploy the infrastructure first using: cd infrastructure && cdk deploy');
      process.exit(1);
    }
    
    const outputs = JSON.parse(fs.readFileSync(cdkOutputsPath, 'utf8'));
    const stackName = Object.keys(outputs)[0];
    
    if (!stackName) {
      console.error('❌ Error: No stack found in cdk-outputs.json');
      process.exit(1);
    }
    
    const stackOutputs = outputs[stackName];
    
    return {
      bucketName: stackOutputs.FrontendBucketName,
      distributionId: stackOutputs.CloudFrontDistributionId || extractDistributionId(stackOutputs.CloudFrontUrl),
      cloudFrontUrl: stackOutputs.CloudFrontUrl
    };
  } catch (error) {
    console.error('❌ Error reading CDK outputs:', error.message);
    process.exit(1);
  }
}

function extractDistributionId(cloudFrontUrl) {
  // If we don't have the distribution ID in outputs, we'll need to look it up
  // For now, return null and handle it gracefully
  return null;
}

// Check if AWS CLI is available
function checkAwsCli() {
  try {
    execFileSync('aws', ['--version'], { stdio: 'ignore' });
    return true;
  } catch (error) {
    console.error('❌ Error: AWS CLI is not installed or not in PATH');
    console.error('   Please install AWS CLI: https://aws.amazon.com/cli/');
    return false;
  }
}

// Sync files to S3
function syncToS3(bucketName) {
  const distPath = path.join(__dirname, 'dist/public-comment-app/browser');
  
  if (!fs.existsSync(distPath)) {
    console.error('❌ Error: Build output not found at', distPath);
    console.error('   Please run: npm run build:prod');
    process.exit(1);
  }
  
  console.log(`📦 Syncing files to S3 bucket: ${bucketName}`);

  const awsProfile = process.env.AWS_PROFILE || 'default';
  const syncArgs = ['s3', 'sync', distPath, `s3://${bucketName}/`, '--delete', '--profile', awsProfile];

  if (isDryRun) {
    console.log(`   [DRY RUN] Would execute: aws ${syncArgs.join(' ')}`);
    return;
  }

  try {
    execFileSync('aws', syncArgs, { stdio: 'inherit' });
    console.log('✅ Files synced successfully');
  } catch (error) {
    console.error('❌ Error syncing files to S3:', error.message);
    process.exit(1);
  }
}

// Set cache control headers for static assets
function setCacheHeaders(bucketName) {
  console.log('⚙️  Setting cache control headers...');

  const longCacheArgs = [
    's3', 'cp',
    `s3://${bucketName}/`, `s3://${bucketName}/`,
    '--recursive',
    '--exclude', '*',
    '--include', '*.js',
    '--include', '*.css',
    '--cache-control', 'public, max-age=31536000, immutable',
    '--metadata-directive', 'REPLACE',
  ];

  const shortCacheArgs = [
    's3', 'cp',
    `s3://${bucketName}/index.html`, `s3://${bucketName}/index.html`,
    '--cache-control', 'public, max-age=0, must-revalidate',
    '--metadata-directive', 'REPLACE',
  ];

  if (isDryRun) {
    console.log(`   [DRY RUN] Would set long cache for JS/CSS files`);
    console.log(`   [DRY RUN] Would set short cache for index.html`);
    return;
  }

  try {
    execFileSync('aws', longCacheArgs, { stdio: 'ignore' });
    execFileSync('aws', shortCacheArgs, { stdio: 'ignore' });
    console.log('✅ Cache headers set successfully');
  } catch (error) {
    console.warn('⚠️  Warning: Could not set cache headers:', error.message);
  }
}

// Invalidate CloudFront cache
function invalidateCloudFront(distributionId) {
  if (!distributionId) {
    console.log('⚠️  CloudFront distribution ID not found, skipping cache invalidation');
    console.log('   You may need to manually invalidate the cache in the AWS Console');
    return;
  }
  
  console.log(`🔄 Invalidating CloudFront cache for distribution: ${distributionId}`);

  const awsProfile = process.env.AWS_PROFILE || 'default';
  const invalidateArgs = [
    'cloudfront', 'create-invalidation',
    '--distribution-id', distributionId,
    '--paths', '/*',
    '--profile', awsProfile,
  ];

  if (isDryRun) {
    console.log(`   [DRY RUN] Would execute: aws ${invalidateArgs.join(' ')}`);
    return;
  }

  try {
    execFileSync('aws', invalidateArgs, { stdio: 'inherit' });
    console.log('✅ CloudFront cache invalidation initiated');
  } catch (error) {
    console.error('❌ Error invalidating CloudFront cache:', error.message);
    console.error('   You may need to manually invalidate the cache in the AWS Console');
  }
}

// Main deployment flow
function deploy() {
  if (!checkAwsCli()) {
    process.exit(1);
  }
  
  const { bucketName, distributionId, cloudFrontUrl } = getCdkOutputs();
  
  console.log(`   Bucket: ${bucketName}`);
  console.log(`   Distribution: ${distributionId || 'Not found'}`);
  console.log(`   URL: ${cloudFrontUrl}\n`);
  
  syncToS3(bucketName);
  setCacheHeaders(bucketName);
  invalidateCloudFront(distributionId);
  
  if (!isDryRun) {
    console.log('\n✨ Deployment complete!');
    console.log(`   Your app is available at: ${cloudFrontUrl}\n`);
  } else {
    console.log('\n✨ Dry run complete! No changes were made.\n');
  }
}

// Run deployment
deploy();
