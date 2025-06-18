# Meraki Automated Migration Tool Suite

A comprehensive suite of tools for automated migration of Meraki switch networks between organizations, including automatic device unclaim/claim via UI automation.

## 🆕 Recent Updates

- **Enhanced Login Compatibility**: Now handles case-sensitive login fields (e.g., "Password" vs "password")
- **2FA Support**: Automatically detects and handles email-based two-factor authentication
- **Improved Chrome Session Management**: Better handling of Chrome processes and session conflicts
- **Dual API Key Support**: Use separate API keys for source and target organizations
- **Enhanced Debugging**: Better error messages and debug output options

## Overview

This tool suite provides both manual and fully automated options for migrating Meraki networks:

### Complete Package Contents

1. **`meraki_migration.py`** - Production-ready migration using environment variables
2. **`meraki_auto_migration.py`** - Full automated migration with UI automation (now with 2FA support)
3. **`meraki_migration_dry_run.py`** - Preview tool to see what will be migrated
4. **`requirements.txt`** - Python dependencies

### Quick Decision Guide

| Scenario | Use This Script |
|----------|----------------|
| Production environment with env vars | `meraki_migration.py` |
| Full automation with inline credentials | `meraki_auto_migration.py` |
| Different API keys for source/target | `meraki_auto_migration.py` with dual keys |
| Preview what will happen (dry run) | `meraki_migration_dry_run.py` |

## What's New: Full Automation with 2FA Support

Unlike manual migration scripts, this tool provides:

1. **Automatic Device Movement** - No manual Dashboard interaction needed
2. **UI Automation with 2FA** - Handles login including email verification codes
3. **Case-Insensitive Field Detection** - Works with various Meraki login page formats
4. **Comprehensive Backup** - Captures ALL settings before migration
5. **Single Command Migration** - Complete migration in one command
6. **Preview Mode** - See what will happen before running

## Prerequisites

### System Requirements

#### For Ubuntu/Debian:
```bash
# Update system
sudo apt-get update

# Install Chrome
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
sudo apt-get update
sudo apt-get install google-chrome-stable

# Install ChromeDriver
sudo apt-get install chromium-chromedriver

# Install Python packages
pip install requests selenium psutil
```

#### For macOS:
```bash
# Install Chrome (download from google.com/chrome or use brew)
brew install --cask google-chrome

# Install ChromeDriver
brew install chromedriver

# Install Python packages
pip install requests selenium psutil
```

### Python Packages
```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install requests selenium psutil
```

### Meraki Requirements
- API key(s) with full admin access
- Dashboard login credentials (username/password)
- Organization admin access for both source and target orgs
- Email access for 2FA codes (if enabled)

## Installation

1. Clone or download the repository

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Verify Chrome and ChromeDriver are installed:
```bash
google-chrome --version
chromedriver --version
```

4. If you get Chrome session errors, ensure no Chrome processes are running:
```bash
pkill -9 -f chrome
pkill -9 -f chromedriver
```

## Quick Start

### 1. Preview Migration (Dry Run)
Always start with a preview to see what will be migrated:
```bash
python meraki_migration_dry_run.py \
  --api-key YOUR_API_KEY \
  --source-org SOURCE_ORG_ID \
  --source-network SOURCE_NETWORK_ID \
  --target-org TARGET_ORG_ID
```

### 2. Run Migration with Same API Key
If using the same API key for both organizations:
```bash
python meraki_auto_migration.py \
  --api-key YOUR_API_KEY \
  --username your.email@company.com \
  --password YOUR_PASSWORD \
  --source-org SOURCE_ORG_ID \
  --source-network SOURCE_NETWORK_ID \
  --target-org TARGET_ORG_ID
```

### 3. Run Migration with Different API Keys
If source and target organizations require different API keys:
```bash
python meraki_auto_migration.py \
  --source-api-key SOURCE_API_KEY \
  --target-api-key TARGET_API_KEY \
  --username your.email@company.com \
  --password YOUR_PASSWORD \
  --source-org SOURCE_ORG_ID \
  --source-network SOURCE_NETWORK_ID \
  --target-org TARGET_ORG_ID
```

### 4. Run in Headless Mode (for servers)
Add `--headless` to run without a visible browser window:
```bash
python meraki_auto_migration.py \
  --api-key YOUR_API_KEY \
  --username your.email@company.com \
  --password YOUR_PASSWORD \
  --source-org SOURCE_ORG_ID \
  --source-network SOURCE_NETWORK_ID \
  --target-org TARGET_ORG_ID \
  --headless
```

## Handling Two-Factor Authentication (2FA)

The tool now automatically handles email-based 2FA:

1. **Detection**: The script automatically detects when 2FA is required
2. **Notification**: You'll see a prompt like:
   ```
   ============================================================
   2FA VERIFICATION REQUIRED
   ============================================================
   Please check your email for the verification code.
   Enter verification code (or press Enter after entering in browser): 
   ```
3. **Options**:
   - **Option A**: Type the code in the terminal and press Enter
   - **Option B**: Type the code directly in the browser, then press Enter in terminal
4. **Automatic Continuation**: The script continues automatically after verification

### 2FA Tips
- Have your email ready before starting the migration
- The script will wait for you to enter the code
- In headless mode, you must enter the code in the terminal
- Consider temporarily disabling 2FA for automation-heavy workflows

## Debug Mode

Enable detailed logging with the `--debug` flag:
```bash
python meraki_auto_migration.py \
  --api-key YOUR_API_KEY \
  --username your.email@company.com \
  --password YOUR_PASSWORD \
  --source-org SOURCE_ORG_ID \
  --source-network SOURCE_NETWORK_ID \
  --target-org TARGET_ORG_ID \
  --debug
```

This will show:
- Which selectors are being used for login fields
- Detailed API call information
- Chrome driver initialization details
- Step-by-step progress through the UI automation

## What Gets Migrated

### Network-Level Settings
- **Switch Configuration**: STP, MTU, storm control
- **Access Control**: ACLs, access policies, 802.1X settings
- **Quality of Service**: QoS rules, DSCP mappings
- **DHCP**: Server policies, DHCP options
- **Monitoring**: SNMP, syslog, NetFlow, alerts
- **Scheduling**: Port schedules
- **Routing**: OSPF, multicast, static routes (where applicable)

### Device-Level Settings
- **Port Configurations**: All settings including VLAN, PoE, STP guard
- **Management Interface**: IP settings, VLAN assignment
- **Layer 3 Settings**: Interfaces, routes (for L3 switches)
- **DHCP Server**: Configured subnets (for L3 switches)

## Migration Process

The automated migration follows these steps:

1. **Login & Authentication**
   - Logs into Meraki Dashboard
   - Handles case-sensitive fields automatically
   - Manages 2FA if enabled

2. **Backup Phase** (via Source API)
   - Downloads all network configurations
   - Saves comprehensive backup to JSON

3. **Device Movement** (via UI Automation)
   - Navigates to source organization
   - Unclaims all devices
   - Waits 120 seconds (Meraki requirement)
   - Claims devices in target organization

4. **Network Creation** (via Target API)
   - Creates network in target organization
   - Adds all devices to the network

5. **Restoration Phase** (via Target API)
   - Applies all network-level settings
   - Configures each device individually

## Troubleshooting

### Chrome Session Conflicts
```
Error: session not created: user data directory already in use
```
**Solution**:
```bash
# Kill all Chrome processes
pkill -9 -f chrome
pkill -9 -f chromedriver

# Clear Chrome temp files
rm -rf /tmp/.com.google.Chrome.*
rm -rf /tmp/chrome*
rm -rf /tmp/meraki_chrome*

# Retry the migration
```

### Login Field Not Found
```
Error: Could not find password field
```
**Solution**: The script now handles case variations automatically. If issues persist:
- Check if the login page has changed significantly
- Try the debug mode to see what's happening
- Ensure you're not hitting a CAPTCHA

### 2FA Timeout
```
Error: Dashboard did not load after login
```
**Solution**: 
- Enter the 2FA code more quickly
- Check if the code was entered correctly
- Ensure no additional security prompts are appearing

### Device Claim Failures
- Ensure devices are fully unclaimed (wait the full 120 seconds)
- Check if devices are online and accessible
- Verify organization has available licenses

### API Rate Limiting
The script handles rate limiting automatically, but if issues persist:
- Add `--debug` to see rate limit headers
- Increase wait times in the script
- Run during off-peak hours

## Advanced Usage

### Custom Target Network Name
Specify a custom name for the target network:
```bash
python meraki_auto_migration.py \
  --api-key YOUR_API_KEY \
  --username your.email@company.com \
  --password YOUR_PASSWORD \
  --source-org SOURCE_ORG_ID \
  --source-network SOURCE_NETWORK_ID \
  --target-org TARGET_ORG_ID \
  --target-network-name "New Network Name"
```

### Batch Migrations
Create a wrapper script for multiple networks:
```python
#!/usr/bin/env python3
import subprocess
import time

networks = [
    ("SOURCE_ORG", "L_123456789", "TARGET_ORG", "Network 1"),
    ("SOURCE_ORG", "L_987654321", "TARGET_ORG", "Network 2"),
]

for source_org, network_id, target_org, name in networks:
    cmd = [
        "python3", "meraki_auto_migration.py",
        "--api-key", "YOUR_API_KEY",
        "--username", "your.email@company.com",
        "--password", "YOUR_PASSWORD",
        "--source-org", source_org,
        "--source-network", network_id,
        "--target-org", target_org,
        "--target-network-name", name,
        "--headless"
    ]
    
    print(f"Migrating {name}...")
    subprocess.run(cmd)
    
    print("Waiting 5 minutes before next migration...")
    time.sleep(300)
```

### Using with CI/CD
```yaml
# GitHub Actions example
name: Meraki Migration
on:
  workflow_dispatch:
    inputs:
      source_network:
        description: 'Source Network ID'
        required: true

jobs:
  migrate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      
      - name: Install Chrome
        run: |
          wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
          sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
          sudo apt-get update
          sudo apt-get install google-chrome-stable chromium-chromedriver
      
      - name: Install Dependencies
        run: pip install -r requirements.txt
      
      - name: Run Migration
        env:
          MERAKI_API_KEY: ${{ secrets.MERAKI_API_KEY }}
          MERAKI_USERNAME: ${{ secrets.MERAKI_USERNAME }}
          MERAKI_PASSWORD: ${{ secrets.MERAKI_PASSWORD }}
        run: |
          python meraki_auto_migration.py \
            --api-key $MERAKI_API_KEY \
            --username $MERAKI_USERNAME \
            --password $MERAKI_PASSWORD \
            --source-org ${{ secrets.SOURCE_ORG }} \
            --source-network ${{ github.event.inputs.source_network }} \
            --target-org ${{ secrets.TARGET_ORG }} \
            --headless
```

## Security Best Practices

1. **Never commit credentials** to version control
2. **Use environment variables** in production environments
3. **Rotate API keys** regularly
4. **Limit script access** to authorized personnel only
5. **Encrypt backup files** containing sensitive configurations
6. **Use service accounts** with minimum required permissions
7. **Enable audit logging** in Meraki Dashboard

## Known Limitations

- Devices must be online during migration
- Historical data and analytics are not migrated
- Client-specific settings are not preserved
- Some organization-specific settings require manual configuration
- Custom dashboard pages and reports are not migrated
- Webhook configurations need manual setup

## Support

For issues:
1. Check the generated log files for detailed error messages
2. Run with `--debug` flag for verbose output
3. Ensure all prerequisites are properly installed
4. Verify Meraki API status: https://status.meraki.com/

### Common Issues Reference

| Issue | Solution |
|-------|----------|
| Chrome won't start | Reinstall Chrome and ChromeDriver, check versions match |
| Login fails | Check credentials, handle 2FA, check for CAPTCHA |
| Devices won't unclaim | Ensure admin permissions, check if devices are in use |
| API errors | Verify API key permissions, check rate limits |
| Timeout errors | Increase wait times, check network connectivity |

## License

These scripts are provided as-is for network administrators to migrate their own Meraki networks. Always test thoroughly in a lab environment before using in production.

## Changelog

### v2.0.0 (Latest)
- Added support for case-sensitive login fields
- Implemented 2FA authentication handling
- Improved Chrome session management
- Added dual API key support for cross-org migrations
- Enhanced error handling and debugging options
- Added psutil for better process management

### v1.0.0
- Initial release with basic automation capabilities
