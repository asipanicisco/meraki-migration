# Meraki Automated Migration Tool Suite

A comprehensive suite of tools for automated migration of Meraki switch networks between organizations, including automatic device unclaim/claim via UI automation.

## Overview

This tool suite provides both manual and fully automated options for migrating Meraki networks:

### Complete Package Contents

1. **`meraki_migration.py`** - Production-ready migration using environment variables (formerly secure_migration.py)
2. **`meraki_auto_migration.py`** - Full automated migration with UI automation
3. **`meraki_migration_dry_run.py`** - Preview tool to see what will be migrated
4. **`requirements.txt`** - Python dependencies

### Quick Decision Guide

| Scenario | Use This Script |
|----------|----------------|
| Production environment with env vars | `meraki_migration.py` |
| Full automation with inline credentials | `meraki_auto_migration.py` |
| Preview what will happen (dry run) | `meraki_migration_dry_run.py` |

## What's New: Full Automation

Unlike manual migration scripts, this tool provides:

1. **Automatic Device Movement** - No manual Dashboard interaction needed
2. **UI Automation** - Handles unclaim/claim process automatically
3. **Comprehensive Backup** - Captures ALL settings before migration
4. **Single Command Migration** - Complete migration in one command
5. **Preview Mode** - See what will happen before running

## Manual vs Automated Comparison

| Task | Manual Process | This Tool |
|------|---------------|-----------|
| Backup settings | Run script | ✅ Automatic |
| Unclaim devices | Login to Dashboard, select, remove | ✅ Automatic |
| Wait for processing | Set timer manually | ✅ Automatic |
| Claim devices | Login to Dashboard, enter serials | ✅ Automatic |
| Create network | Run script or Dashboard | ✅ Automatic |
| Add devices | Dashboard clicks | ✅ Automatic |
| Restore settings | Run script | ✅ Automatic |
| **Total Time** | 30-60 minutes | **5-10 minutes** |
| **Human Steps** | 10+ manual steps | **1 command** |

## Features

### Complete Automation
1. **Comprehensive Backup** (via API)
   - All network-level settings (STP, MTU, ACLs, SNMP, etc.)
   - All device-level settings (ports, routing, DHCP, management IPs)
   - All security and monitoring configurations

2. **Automated Device Movement** (via UI automation)
   - Automatically unclaims devices from source organization
   - Waits for processing
   - Automatically claims devices in target organization
   - No manual Dashboard interaction required!

3. **Automatic Network Creation & Restoration** (via API)
   - Creates new network in target organization
   - Adds all devices to the network
   - Restores all backed-up settings

## Prerequisites

### Python Packages
```bash
pip install requests selenium
```

### Chrome Driver
Download ChromeDriver matching your Chrome version:
- Visit: https://chromedriver.chromium.org/
- Download the version matching your Chrome browser
- Add to PATH or place in script directory

### Meraki Requirements
- API key with full admin access
- Dashboard login credentials (username/password)
- Organization admin access for both source and target orgs

## Installation

1. Install required packages:
```bash
pip install -r requirements.txt
```

2. Download ChromeDriver:
```bash
# On macOS with Homebrew
brew install chromedriver

# On Ubuntu/Debian
sudo apt-get install chromium-chromedriver

# Or download manually from https://chromedriver.chromium.org/
```

3. Verify ChromeDriver installation:
```bash
chromedriver --version
```

## Quick Start

1. **Preview migration (dry run):**
   ```bash
   python meraki_migration_dry_run.py \
     --api-key YOUR_API_KEY \
     --source-org SOURCE_ORG_ID \
     --source-network SOURCE_NETWORK_ID \
     --target-org TARGET_ORG_ID
   ```

2. **Run migration (production with env vars):**
   ```bash
   # Set environment variables
   export MERAKI_API_KEY='your-api-key'
   export MERAKI_USERNAME='your-email@company.com'
   export MERAKI_PASSWORD='your-password'
   
   # Run migration
   python meraki_migration.py SOURCE_ORG_ID SOURCE_NETWORK_ID TARGET_ORG_ID
   ```

3. **Run migration (with inline credentials):**
   ```bash
   python meraki_auto_migration.py \
     --api-key YOUR_API_KEY \
     --username your.email@company.com \
     --password YOUR_PASSWORD \
     --source-org SOURCE_ORG_ID \
     --source-network SOURCE_NETWORK_ID \
     --target-org TARGET_ORG_ID
   ```

## Available Scripts

### 1. Production Migration Script (`meraki_migration.py`)
Uses environment variables for credentials (recommended for production).

```bash
# Set environment variables
export MERAKI_API_KEY='your-api-key'
export MERAKI_USERNAME='your-email@company.com'
export MERAKI_PASSWORD='your-password'

# Run migration
python meraki_migration.py SOURCE_ORG_ID SOURCE_NETWORK_ID TARGET_ORG_ID
```

### 2. Full Automation Script (`meraki_auto_migration.py`)
Full automated migration with UI automation for device movement.

```bash
python meraki_auto_migration.py \
  --api-key YOUR_API_KEY \
  --username your.email@company.com \
  --password YOUR_PASSWORD \
  --source-org SOURCE_ORG_ID \
  --source-network SOURCE_NETWORK_ID \
  --target-org TARGET_ORG_ID \
  --target-network-name "Optional Custom Name"
```

### 3. Migration Preview Script (`meraki_migration_dry_run.py`)
Preview what will be migrated without making any changes.

```bash
python meraki_migration_dry_run.py \
  --api-key YOUR_API_KEY \
  --source-org SOURCE_ORG_ID \
  --source-network SOURCE_NETWORK_ID \
  --target-org TARGET_ORG_ID \
  --save-preview preview.json
```

## What Gets Migrated

### Network-Level Settings
- **STP Configuration**: Bridge priorities, RSTP settings
- **MTU Settings**: Custom MTU values
- **Access Control Lists (ACLs)**: All configured ACLs
- **Access Policies**: 802.1X, MAB, and guest policies
- **SNMP v2/v3**: Community strings, users, trap receivers
- **QoS Rules**: Traffic prioritization
- **DHCP Settings**: Server policies, options
- **Port Schedules**: Time-based port control
- **Storm Control**: Broadcast/multicast limits
- **Link Aggregations**: LACP configurations
- **Routing**: OSPF, multicast, static routes

### Device-Level Settings
- **All Port Configurations**:
  - Access/trunk modes
  - VLAN assignments
  - PoE settings
  - Port names and descriptions
  - STP guard settings
  - Port isolation
  - Speed/duplex
  - Port schedules
- **Management Interface**:
  - Static IP or DHCP
  - VLAN assignment
  - DNS servers
- **Layer 3 Interfaces**: (if applicable)
  - Interface IPs
  - VLAN interfaces
  - Static routes
- **DHCP Server**: Configured subnets and options

### Monitoring & Alerts
- Syslog servers
- NetFlow collectors
- Alert settings
- SNMP trap receivers

## Migration Process

The script performs these steps automatically:

1. **Backup Phase** (API)
   - Connects to source network
   - Downloads all configurations
   - Saves backup to JSON file

2. **Device Movement** (UI Automation)
   - Logs into Meraki Dashboard
   - Navigates to source organization
   - Selects and unclaims all devices
   - Waits 120 seconds for processing
   - Switches to target organization
   - Claims all devices using serials

3. **Network Setup** (API)
   - Creates new network in target org
   - Adds all claimed devices to network

4. **Restoration Phase** (API)
   - Applies all network-level settings
   - Configures each device individually
   - Restores all port configurations

## ⚠️ Important Warnings

### When to Use This Tool
- ✅ Moving networks between your own organizations
- ✅ Lab or test environments
- ✅ Planned maintenance windows
- ✅ When you have full admin access to both orgs

### When NOT to Use
- ❌ Production networks during business hours
- ❌ Without proper change control approval
- ❌ If you're not certain about the target organization
- ❌ Without testing in a lab first

### Before Running
1. **Always run preview mode first** to see what will be migrated
2. **Test with a small network** before migrating large deployments
3. **Schedule a maintenance window** - devices will be briefly offline
4. **Have a rollback plan** - keep your backup files

## Security

### Best Practices
- **Credentials**: Use environment variables in production (`meraki_migration.py`)
- **API Key**: Keep your API key secure and never commit to version control
- **Backup Files**: Contain sensitive network configurations - store securely
- **Access Control**: Limit who can run these scripts

### Using Environment Variables (Recommended)
```bash
# Set once in your shell profile or CI/CD system
export MERAKI_API_KEY='your-api-key'
export MERAKI_USERNAME='your-email@company.com'
export MERAKI_PASSWORD='your-password'

# Then run without exposing credentials
python meraki_migration.py SOURCE_ORG SOURCE_NET TARGET_ORG
```

## Advanced Usage

### Running Headless (No Browser Window)
Edit `meraki_auto_migration.py` and change:
```python
with MerakiUIAutomation(self.username, self.password, headless=True) as ui:
```

### Custom Wait Times
Modify sleep durations in the script:
```python
# After unclaim (default 120 seconds)
time.sleep(180)  # Increase to 3 minutes

# After claim (default 30 seconds)  
time.sleep(60)   # Increase to 1 minute
```

### Using with CI/CD
```yaml
# Example GitHub Actions
env:
  MERAKI_API_KEY: ${{ secrets.MERAKI_API_KEY }}
  MERAKI_USERNAME: ${{ secrets.MERAKI_USERNAME }}
  MERAKI_PASSWORD: ${{ secrets.MERAKI_PASSWORD }}

steps:
  - name: Run Migration
    run: python meraki_migration.py $SOURCE_ORG $SOURCE_NET $TARGET_ORG
```

### Batch Migrations
Create a script to migrate multiple networks:
```python
networks = [
    ("L_1234", "Network 1"),
    ("L_5678", "Network 2"),
]

for network_id, name in networks:
    tool.execute_migration(source_org, network_id, target_org, name)
    time.sleep(300)  # Wait between migrations
```

## Complete Workflow Example

```bash
# 1. Preview what will happen
python meraki_migration_dry_run.py \
  --api-key YOUR_KEY \
  --source-org 123456 \
  --source-network L_123456789 \
  --target-org 654321 \
  --save-preview migration_plan.json

# 2. Review the preview
cat migration_plan.json

# 3. Set environment variables (for production)
export MERAKI_API_KEY='your-key'
export MERAKI_USERNAME='admin@company.com'
export MERAKI_PASSWORD='your-password'

# 4. Run the migration
python meraki_migration.py 123456 L_123456789 654321

# 5. Verify completion in Dashboard
```

## Timing

- The script waits 120 seconds after unclaiming devices (required by Meraki)
- Additional waits ensure operations complete successfully
- Total migration time: ~5-10 minutes depending on network size

## Browser Automation

- The script uses Chrome in visible mode by default
- You can run headless by modifying the script
- Ensure your Chrome browser is up to date
- Don't interact with the browser while script is running

## Limitations

- Devices must be online and accessible
- Some organization-specific settings may need manual configuration
- Historical data and analytics are not migrated
- Client-specific settings are not preserved

## Troubleshooting

### ChromeDriver Issues
```
Error: 'chromedriver' executable needs to be in PATH
```
Solution: Ensure ChromeDriver is installed and in your system PATH

### Login Failures
- Verify credentials are correct
- Check if 2FA is enabled (may need to disable temporarily)
- Ensure no CAPTCHA is required

### Device Claim Failures
- Devices may still be registered to previous organization
- Wait longer between unclaim and claim (increase sleep time)
- Check if devices are online

### API Rate Limits
- The script handles rate limiting automatically
- If issues persist, add longer delays between operations

## Example Output

```
2024-01-15 10:30:00 - INFO - Starting migration with user: admin@company.com
2024-01-15 10:30:00 - INFO - ==================================================
2024-01-15 10:30:00 - INFO - STEP 1: Backing up all settings
2024-01-15 10:30:00 - INFO - ==================================================
2024-01-15 10:30:01 - INFO - Starting comprehensive backup for network L_123456789
2024-01-15 10:30:02 - INFO - Found 12 devices
2024-01-15 10:30:03 - INFO - Backed up switch stp
2024-01-15 10:30:04 - INFO - Backed up switch mtu
2024-01-15 10:30:15 - INFO - Backed up 48 ports for Q2XX-XXXX-XXXX
2024-01-15 10:30:25 - INFO - Backup saved to migration_backup_L_123456789_20240115_103000.json
2024-01-15 10:30:25 - INFO - ==================================================
2024-01-15 10:30:25 - INFO - STEP 2: Moving devices via UI automation
2024-01-15 10:30:25 - INFO - ==================================================
2024-01-15 10:30:26 - INFO - Chrome driver initialized
2024-01-15 10:30:28 - INFO - Successfully logged in
2024-01-15 10:30:35 - INFO - Successfully unclaimed 12 devices
2024-01-15 10:30:35 - INFO - Waiting 120 seconds for unclaim to process...
2024-01-15 10:32:35 - INFO - Successfully claimed 12 devices
2024-01-15 10:33:05 - INFO - ==================================================
2024-01-15 10:33:05 - INFO - STEP 3: Creating network and adding devices
2024-01-15 10:33:05 - INFO - ==================================================
2024-01-15 10:33:06 - INFO - Created network: L_987654321
2024-01-15 10:33:07 - INFO - Devices added to network
2024-01-15 10:33:17 - INFO - ==================================================
2024-01-15 10:33:17 - INFO - STEP 4: Restoring all settings
2024-01-15 10:33:17 - INFO - ==================================================
2024-01-15 10:33:18 - INFO - Restored STP settings
2024-01-15 10:33:19 - INFO - Restored MTU settings
2024-01-15 10:33:45 - INFO - ==================================================
2024-01-15 10:33:45 - INFO - MIGRATION COMPLETE!
2024-01-15 10:33:45 - INFO - Target Network ID: L_987654321
2024-01-15 10:33:45 - INFO - ==================================================
```

## Backup File Structure

The script creates a comprehensive backup file containing:

```json
{
  "timestamp": "2024-01-15T10:30:00",
  "org_id": "123456",
  "org_name": "Source Organization",
  "network_id": "L_123456789",
  "network_info": {...},
  "devices": [...],
  "network_settings": {
    "switch": {
      "stp": {...},
      "mtu": {...},
      "accessPolicies": [...],
      ...
    },
    "routing": {...},
    "security": {...},
    "monitoring": {...}
  },
  "device_settings": {
    "Q2XX-XXXX-XXXX": {
      "ports": [...],
      "management": {...},
      "routing": {...},
      "dhcp": {...}
    }
  }
}
```

## Frequently Asked Questions

### Q: How long will devices be offline?
**A:** Typically 3-5 minutes during the unclaim/claim process. The 120-second wait is mandatory.

### Q: Can I migrate between different organization types?
**A:** Yes, but ensure both organizations have appropriate licensing for the devices.

### Q: What if the migration fails midway?
**A:** The backup file contains all settings. You can manually reclaim devices and run the restore portion.

### Q: Can I use this with 2FA enabled?
**A:** You may need to temporarily disable 2FA or use an admin account without 2FA for automation.

### Q: Will client devices need to reconnect?
**A:** Yes, wireless clients will need to reconnect. Wired clients may experience a brief disconnection.

### Q: Can I modify what gets migrated?
**A:** Yes, you can edit the backup JSON file before restoration to exclude certain settings.

### Q: Does this work with all switch models?
**A:** Yes, it supports all MS series switches. The script detects model types automatically.

### Q: What about switch stacks?
**A:** Stack configurations are preserved, but ensure all stack members are migrated together.

## Support

For issues:
- Check the log file generated in the same directory
- Ensure all prerequisites are met
- Verify network connectivity
- Check Meraki API status: https://status.meraki.com/

### Support Resources
- **Meraki API**: https://developer.cisco.com/meraki/api-v1/
- **ChromeDriver**: https://chromedriver.chromium.org/
- **Selenium Docs**: https://selenium-python.readthedocs.io/
- **Meraki Community**: https://community.meraki.com/

## License

These scripts are provided as-is for network administrators to migrate their own Meraki networks. Always test thoroughly before using in production.
