#!/usr/bin/env node

/**
 * Verification script for build configuration
 * 
 * This script checks that the build configuration is correct for S3/CloudFront deployment
 */

const fs = require('fs');
const path = require('path');

console.log('🔍 Verifying build configuration...\n');

let hasErrors = false;

// Check angular.json
function checkAngularJson() {
  console.log('📋 Checking angular.json...');
  
  const angularJsonPath = path.join(__dirname, 'angular.json');
  if (!fs.existsSync(angularJsonPath)) {
    console.error('   ❌ angular.json not found');
    hasErrors = true;
    return;
  }
  
  const angularJson = JSON.parse(fs.readFileSync(angularJsonPath, 'utf8'));
  const prodConfig = angularJson.projects['public-comment-app'].architect.build.configurations.production;
  
  // Check base href
  if (prodConfig.baseHref === '/') {
    console.log('   ✅ Base href is set to "/" for CloudFront');
  } else {
    console.error(`   ❌ Base href should be "/" but is "${prodConfig.baseHref || 'not set'}"`);
    hasErrors = true;
  }
  
  // Check output hashing
  if (prodConfig.outputHashing === 'all') {
    console.log('   ✅ Output hashing is enabled');
  } else {
    console.warn(`   ⚠️  Output hashing is "${prodConfig.outputHashing}" (should be "all")`);
  }
  
  // Check file replacements
  const hasEnvReplacement = prodConfig.fileReplacements?.some(
    fr => fr.replace.includes('environment.ts') && fr.with.includes('environment.prod.ts')
  );
  
  if (hasEnvReplacement) {
    console.log('   ✅ Environment file replacement configured');
  } else {
    console.error('   ❌ Environment file replacement not configured');
    hasErrors = true;
  }
}

// Check environment files
function checkEnvironmentFiles() {
  console.log('\n📋 Checking environment files...');
  
  const envPath = path.join(__dirname, 'src/environments/environment.ts');
  const envProdPath = path.join(__dirname, 'src/environments/environment.prod.ts');
  
  if (!fs.existsSync(envPath)) {
    console.error('   ❌ environment.ts not found');
    hasErrors = true;
    return;
  }
  
  if (!fs.existsSync(envProdPath)) {
    console.error('   ❌ environment.prod.ts not found');
    hasErrors = true;
    return;
  }
  
  console.log('   ✅ Environment files exist');
  
  const envProdContent = fs.readFileSync(envProdPath, 'utf8');
  
  if (envProdContent.includes("apiBaseUrl: '/api'")) {
    console.log('   ✅ Production API base URL is set to relative path "/api"');
  } else {
    console.error('   ❌ Production API base URL should be "/api" for CloudFront');
    hasErrors = true;
  }
  
  if (envProdContent.includes('production: true')) {
    console.log('   ✅ Production flag is set to true');
  } else {
    console.error('   ❌ Production flag should be true');
    hasErrors = true;
  }
}

// Check package.json scripts
function checkPackageJson() {
  console.log('\n📋 Checking package.json scripts...');
  
  const packageJsonPath = path.join(__dirname, 'package.json');
  if (!fs.existsSync(packageJsonPath)) {
    console.error('   ❌ package.json not found');
    hasErrors = true;
    return;
  }
  
  const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'));
  const scripts = packageJson.scripts || {};
  
  if (scripts['build:prod']) {
    console.log('   ✅ build:prod script exists');
  } else {
    console.error('   ❌ build:prod script not found');
    hasErrors = true;
  }
  
  if (scripts['deploy']) {
    console.log('   ✅ deploy script exists');
  } else {
    console.error('   ❌ deploy script not found');
    hasErrors = true;
  }
  
  if (scripts['deploy:dry-run']) {
    console.log('   ✅ deploy:dry-run script exists');
  } else {
    console.warn('   ⚠️  deploy:dry-run script not found (optional)');
  }
}

// Check deployment script
function checkDeploymentScript() {
  console.log('\n📋 Checking deployment script...');
  
  const deployScriptPath = path.join(__dirname, 'deploy.js');
  if (fs.existsSync(deployScriptPath)) {
    console.log('   ✅ deploy.js exists');
    
    // Check if it's executable
    try {
      fs.accessSync(deployScriptPath, fs.constants.X_OK);
      console.log('   ✅ deploy.js is executable');
    } catch {
      console.log('   ℹ️  deploy.js is not executable (will be run via node)');
    }
  } else {
    console.error('   ❌ deploy.js not found');
    hasErrors = true;
  }
}

// Run all checks
checkAngularJson();
checkEnvironmentFiles();
checkPackageJson();
checkDeploymentScript();

// Summary
console.log('\n' + '='.repeat(50));
if (hasErrors) {
  console.log('❌ Build configuration has errors. Please fix them before deploying.');
  process.exit(1);
} else {
  console.log('✅ Build configuration is correct!');
  console.log('\nYou can now:');
  console.log('  1. Build for production: npm run build:prod');
  console.log('  2. Deploy to S3/CloudFront: npm run deploy');
  console.log('  3. Or do a dry run: npm run deploy:dry-run');
  process.exit(0);
}
