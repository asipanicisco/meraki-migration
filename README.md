# Meraki Network Migration Tool

Automated tool for migrating Meraki networks between organizations with complete configuration backup and restore.

## Overview

This tool automates the complex process of migrating a Meraki network from one organization to another, preserving all configurations, settings, and device assignments.

### Migration Process

1. **Verify Access** - Confirms API access to source and target organizations
2. **Comprehensive Backup** - Backs up all network and device configurations via API
3. **Remove from Network** - Removes devices from their current network via UI automation
4. **Unclaim Devices** - Unclaims devices from the source organization via UI automation
5. **Claim Devices** - Claims devices in the target organization via UI automation
6. **Create Network** - Creates a new network in the target organization via API
7. **Add Devices** - Assigns devices to the new network via API
8. **Restore Configuration** - Restores all backed-up settings via API

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
- **Two API keys**: One for the source organization and one for the target organization
- **Dashboard admin credentials** with appropriate permissions
- **2FA configured** on your Meraki account

## Usage

### Command Line Arguments

```bash
python3 migrate.py \
    --source-api-key "YOUR_SOURCE_API_KEY" \
    --target-api-key "YOUR_TARGET_API_KEY" \
    --username "your.email@example.com" \
    --password "your_password" \
    --source-org-id "123456" \
    --source-org-name "Source Organization Name" \
    --source-network-id "N_123456789" \
    --source-network-name "Network Name" \
    --target-org-id "789012" \
    --target-org-name "Target Organization Name" \
    --target-network-name "New Network Name"
```

### Required Parameters

- `--source-api-key`: API key for the source organization
- `--target-api-key`: API key for the target organization
- `--username`: Meraki Dashboard username (email)
- `--password`: Meraki Dashboard password
- `--source-org-id`: Source organization ID
- `--source-org-name`: Source organization name (must match Dashboard exactly)
- `--source-network-id`: Source network ID to migrate
- `--source-network-name`: Source network name (must match Dashboard exactly)
- `--target-org-id`: Target organization ID
- `--target-org-name`: Target organization name (must match Dashboard exactly)

### Optional Parameters

- `--target-network-name`: Name for the new network (defaults to source name + "_migrated")
- `--headless`: Run Chrome in headless mode (for server environments)
- `--debug`: Enable debug logging for troubleshooting

## Finding Required Information

### Organization ID and Name
1. Log into Meraki Dashboard
2. Select your organization
3. The URL will contain the org ID: `https://nXXX.meraki.com/o/XXXXXX/manage/`
4. The org ID is the string after `/o/` (e.g., `123456`)
5. The org name is shown in the organization selector dropdown

### Network ID and Name
1. Navigate to a network
2. The URL will contain the network ID: `.../networks/N_XXXXXXXXXXXXX/...`
3. The network ID starts with `N_` or `L_`
4. The network name is shown in the network selector

### API Keys
1. Go to **Organization > Settings**
2. Under "Dashboard API access", enable API access
3. Click **Generate new API key**
4. **Important**: Save the key immediately - it's only shown once!

## 2FA Handling

The tool automatically detects when 2FA is required and prompts you:

```
============================================================
2FA VERIFICATION REQUIRED
============================================================
Please check your email for the verification code.
Enter verification code: 
```

Simply enter the code from your email when prompted, and the script will continue.

## What Gets Migrated

### Network-Level Settings
- **Switch Settings**: STP, MTU, DHCP server policy, storm control
- **Access Policies**: 802.1X policies, port schedules
- **QoS**: QoS rules and DSCP mappings
- **Security**: Access control lists, port security settings
- **Monitoring**: SNMP, syslog servers, NetFlow, alerts
- **Routing**: Static routes, OSPF, multicast settings

### Device-Level Settings
- **Management Interface**: IP configuration
- **Switch Ports**: All port configurations including:
  - VLANs and access policies
  - Port types and speeds
  - PoE settings
  - Port schedules
- **Layer 3**: Routing interfaces, static routes (for L3 switches)
- **DHCP**: DHCP server settings (for L3 switches)

## Output Files

### Backup File
The tool creates a comprehensive backup file:
- Filename: `migration_backup_[NETWORK_ID]_[TIMESTAMP].json`
- Contains all network and device configurations
- Can be used for recovery or documentation

### Log File
Detailed migration log:
- Filename: `meraki_migration_[TIMESTAMP].log`
- Contains all operations performed
- Useful for troubleshooting

## Troubleshooting

### Common Issues

1. **"Failed to select source organization"**
   - Verify the organization name matches exactly what's shown in Dashboard
   - Check that you have access to the organization
   - Try running without `--headless` to see what's happening

2. **ChromeDriver not found**
   - Ensure ChromeDriver is installed and in your PATH
   - Check Chrome and ChromeDriver versions match

3. **Login fails**
   - Verify credentials are correct
   - Ensure 2FA is properly configured
   - Check for any login banners or notices

4. **Devices not unclaimed**
   - Ensure devices have no active clients
   - Check for switch stack dependencies
   - Verify you have full admin permissions

5. **Network removal fails**
   - Confirm the network name is exact
   - Check that devices aren't in critical use
   - Look for any port channel or stack dependencies

### Debug Mode

Run with `--debug` for verbose logging:
```bash
python3 migrate.py --debug ... [other arguments]
```

This provides detailed information about:
- API calls and responses
- UI element searches
- Page navigation steps
- Error details

## Best Practices

1. **Test First**: Always test with a small network or lab environment first
2. **Maintenance Window**: Schedule migrations during maintenance windows
3. **Verify IDs and Names**: Double-check all IDs and names match exactly
4. **Backup**: Keep the generated backup file for recovery purposes
5. **Monitor Progress**: Watch the console output for any issues
6. **Post-Migration**: 
   - Verify all devices are online
   - Check critical configurations
   - Test connectivity
   - Confirm monitoring is working

## Limitations

- **Switch Stacks**: May need to be dissolved before migration
- **Warm Spare**: Configurations may need manual reconfiguration
- **API Limits**: Large networks may hit rate limits (tool handles this automatically)
- **Feature Availability**: Some features may not be available in the target organization

## Security Notes

- Never commit credentials or API keys to version control
- Use environment variables or secure credential storage
- API keys should have only necessary permissions
- Revoke API keys that are no longer needed
- Run the tool from a secure, trusted system

## Support

For Meraki API documentation: https://developer.cisco.com/meraki/api-v1/

For issues with the tool, check:
1. The generated log file for detailed error messages
2. Run with `--debug` for more information
3. Verify all prerequisites are installed correctly
4. Ensure organization and network names match exactly

## Example Migration

```bash
# Migrate a network from one organization to another
python3 migrate.py \
    --source-api-key "abc123..." \
    --target-api-key "xyz789..." \
    --username "admin@company.com" \
    --password "SecurePass123!" \
    --source-org-id "612345" \
    --source-org-name "Company HQ" \
    --source-network-id "N_24729847298" \
    --source-network-name "SF-Office-Switches" \
    --target-org-id "698765" \
    --target-org-name "Company Branch" \
    --target-network-name "SF-Office-Switches-Migrated"
```

This will:
1. Backup all settings from the source network
2. Remove devices from the source network
3. Unclaim devices from the source organization  
4. Claim devices in the target organization
5. Create "SF-Office-Switches-Migrated" in the target org
6. Restore all configurations
