# Meraki Network Migration Tool

This tool automates the migration of Meraki devices between organizations using a combination of API operations and UI automation.

## Overview

The migration process involves:
1. **Backing up** all network and device configurations via API
2. **Removing** devices from their current network via UI automation
3. **Unclaiming** devices from the source organization via UI automation
4. **Claiming** devices in the target organization via UI automation
5. **Creating** a new network in the target organization via API
6. **Restoring** all configurations to the new network via API

**Important**: Devices must be removed from their network before they can be unclaimed from the organization. The tool handles this automatically.

## Prerequisites

### System Requirements
- Python 3.6 or higher
- Google Chrome browser
- ChromeDriver (compatible with your Chrome version)

### Python Dependencies
```bash
pip install -r requirements.txt
```

Required packages:
- `requests` - For API operations
- `selenium` - For UI automation
- `psutil` - For process management (optional but recommended)

### Chrome and ChromeDriver Installation

#### Ubuntu/Debian:
```bash
# Install Chrome
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list'
sudo apt-get update
sudo apt-get install google-chrome-stable

# Install ChromeDriver
sudo apt-get install chromium-chromedriver
```

#### macOS:
```bash
# Using Homebrew
brew install --cask google-chrome
brew install chromedriver
```

### Meraki Requirements
- Two API keys: one for the source organization and one for the target organization
- Dashboard admin credentials with 2FA configured
- Appropriate permissions in both organizations

## Files

### 1. `migrate.py` - Main Migration Tool
The primary script for performing full network migrations.

### 2. `debug.py` - Comprehensive Debug Tool
A debug script for testing individual components and troubleshooting issues.

## Usage

### Full Migration (migrate.py)

Basic usage:
```bash
python3 migrate.py \
    --source-api-key "YOUR_SOURCE_API_KEY" \
    --target-api-key "YOUR_TARGET_API_KEY" \
    --username "your.email@example.com" \
    --password "your_password" \
    --source-org "SOURCE_ORG_ID" \
    --source-network "SOURCE_NETWORK_ID" \
    --target-org "TARGET_ORG_ID" \
    --target-network-name "New Network Name"
```

Options:
- `--source-api-key`: API key for the source organization (required)
- `--target-api-key`: API key for the target organization (required)
- `--username`: Meraki Dashboard username (required)
- `--password`: Meraki Dashboard password (required)
- `--source-org`: Source organization ID (required)
- `--source-network`: Source network ID to migrate (required)
- `--target-org`: Target organization ID (required)
- `--target-network-name`: Name for the new network (optional, defaults to original name + "_migrated")
- `--headless`: Run Chrome in headless mode for server environments
- `--debug`: Enable debug logging

### Debug Tool (debug.py)

The debug tool has three test modes:

#### 1. API Test Mode
Test API connectivity and permissions:
```bash
python3 debug.py --test-mode api \
    --source-api-key "YOUR_API_KEY" \
    --org-id "ORG_ID" \
    --network-id "NETWORK_ID"  # Optional
```

#### 2. UI Test Mode
Test UI automation (login, navigation, unclaim):
```bash
python3 debug.py --test-mode ui \
    --username "your.email@example.com" \
    --password "your_password" \
    --source-org-name "Organization Name" \
    --device-serial "XXXX-XXXX-XXXX" \
    --headless  # Optional
```

#### 3. Full Test Mode
Test the complete migration flow with a single device:
```bash
python3 debug.py --test-mode full \
    --source-api-key "SOURCE_API_KEY" \
    --target-api-key "TARGET_API_KEY" \
    --username "your.email@example.com" \
    --password "your_password" \
    --source-org-name "Source Org Name" \
    --target-org-name "Target Org Name" \
    --network-name "Network Name" \
    --device-serial "XXXX-XXXX-XXXX" \
    --headless  # Optional
```

## Finding Required IDs

### Organization ID
1. Log into Meraki Dashboard
2. Select your organization
3. The URL will contain the org ID: `https://nXXX.meraki.com/o/XXXXXX/manage/`
4. The org ID is the string after `/o/`

### Network ID
1. Navigate to a network
2. The URL will contain the network ID: `https://nXXX.meraki.com/network/list/N_XXXXXXXXXXXXX`
3. The network ID starts with `N_` or `L_`

### API Keys
1. Go to Organization > Settings
2. Under "Dashboard API access", enable API access
3. Generate a new API key (save it securely - it's only shown once)

## 2FA Handling

The tool will automatically detect when 2FA is required and prompt you:
```
============================================================
2FA VERIFICATION REQUIRED
============================================================
Please check your email for the verification code.
Enter verification code: 
```

Enter the code when prompted, and the script will continue automatically.

## Troubleshooting

### Common Issues

1. **ChromeDriver not found**
   - Ensure ChromeDriver is installed and in your PATH
   - You can specify the path explicitly in the script if needed

2. **Login fails**
   - Check credentials
   - Ensure 2FA is properly configured
   - Use debug mode to save screenshots

3. **Organization not found**
   - Verify the organization name/ID is correct
   - Ensure you have access to the organization
   - For org IDs, use the numeric ID, not the name

4. **Devices not unclaimed**
   - Ensure devices are not in use (no active clients)
   - Check that you have appropriate permissions
   - Devices must be removed from their network first (handled automatically)
   - Some devices may have dependencies that prevent unclaim

5. **Network removal fails**
   - Verify you have access to the network
   - Ensure the network name is correct
   - Check that devices aren't part of a switch stack that needs to be dissolved first

### Debug Features

The debug tool creates numbered screenshots at each step:
- `debug_001_login_page_TIMESTAMP.png`
- `debug_002_after_email_TIMESTAMP.png`
- etc.

Use these to diagnose where the process is failing.

### Logs

Both scripts create detailed log files:
- `meraki_migration_YYYYMMDD_HHMMSS.log` (migrate.py)
- Console output with timestamps (debug.py)

## Best Practices

1. **Test First**: Always use debug.py to test with a single device before running a full migration
2. **Off-Hours**: Run migrations during maintenance windows to minimize disruption
3. **Backup**: The tool creates a JSON backup file - keep this for recovery purposes
4. **Verify**: After migration, verify all settings in the Dashboard
5. **API Rate Limits**: The tool handles rate limiting automatically, but large migrations may take time

## Security Notes

- Never commit API keys or passwords to version control
- Use environment variables or secure credential storage
- API keys should have the minimum required permissions
- Revoke API keys that are no longer needed

## Support

For issues specific to the Meraki API, consult the [Meraki API documentation](https://developer.cisco.com/meraki/api-v1/).

For UI changes that break the automation, the selectors in the code may need to be updated.
