### Wait for Devices to Appear
Monitor and wait for devices to be claimed and added:
```bash
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --mode wait \
  --backup-file my_switch_backup.json \
  --target-org TARGET_ORG_ID \
  --target-network TARGET_NETWORK_ID \
  --timeout 600  # Wait up to 10 minutes
```# Meraki Switch Network Migration Tool

A comprehensive Python script designed specifically for backing up and restoring Meraki switch network configurations between organizations and networks, with helper tools to manage the device migration process.

## Operation Modes

The script supports seven operation modes:

1. **`backup`** - Save all network and switch configurations
2. **`restore`** - Apply saved configurations to a new network
3. **`migrate`** - Combined backup and restore operation
4. **`inventory`** - Generate detailed device inventory reports
5. **`verify`** - Check if devices exist in target organization
6. **`wait`** - Monitor and wait for devices to appear after claiming
7. **`prepare`** - Update device notes/tags before migration

## Features

### Complete Switch Network Backup

**Port-Level Settings**:
- Port configurations (access/trunk modes, VLANs, native VLAN)
- Port names and tags
- PoE settings (enabled/disabled, power allocation)
- Port isolation settings
- RSTP/STP settings per port
- Storm control settings
- Port schedules
- Link negotiation settings
- Port mirroring configurations
- UDLD settings

**Switch Network-Level Settings**:
- Switch settings (global configurations)
- Access policies (802.1X, MAB, policies)
- Alternate management interface
- DHCP server policy
- DSCP to CoS mappings
- MTU settings
- Port schedules
- QoS rules
- Storm control (global)
- STP/RSTP settings
- Multicast routing
- OSPF routing
- Warm spare configurations
- Switch stacks
- Link aggregations (LACP)

**Organization-Level Settings** (optional):
- Configuration templates
- Adaptive policy settings (SGTs, ACLs)
- SAML roles
- Policy objects and groups
- Login security settings
- Organization-wide SNMP

**General Network Settings**:
- Network name, timezone, tags
- Group policies
- Alert configurations
- Syslog servers
- SNMP settings
- NetFlow collectors
- Webhooks
- Traffic analysis settings

### Migration Helper Tools

**Device Preparation** (NEW):
- Automatically update device notes with order/claim numbers
- Bulk tag devices for migration tracking
- Generate claim info templates

**Inventory Report Generation**:
- Detailed device inventory with serials, models, IPs
- CSV export for easy reference
- Device count summaries

**Migration Checklist**:
- Auto-generated from backup
- Lists all devices to migrate
- Step-by-step instructions
- Extracts claim info from notes/tags

**Device Verification**:
- Check which devices are in target org
- Identify missing devices
- Verify readiness before restore

**Device Monitoring**:
- Wait for devices to appear after claiming
- Real-time status updates
- Configurable timeout

**Device Mapping**:
- Maps old serials to new ones
- Handles serial number changes
- Ensures configs apply to correct switches

## Prerequisites

```bash
pip install requests
```

## Getting Your Meraki API Key

1. Log into the Meraki Dashboard
2. Go to Organization > Settings
3. Check "Enable access to the Cisco Meraki Dashboard API"
4. Generate your API key

## Usage

### List Organizations
```bash
python meraki_migration.py --api-key YOUR_API_KEY --list-orgs
```

### List Networks in an Organization
```bash
python meraki_migration.py --api-key YOUR_API_KEY --list-networks ORG_ID
```

### Backup a Switch Network
```bash
# Basic backup (network settings only)
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --mode backup \
  --source-org SOURCE_ORG_ID \
  --source-network SOURCE_NETWORK_ID \
  --backup-file my_switch_backup.json

# Include organization-level settings
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --mode backup \
  --source-org SOURCE_ORG_ID \
  --source-network SOURCE_NETWORK_ID \
  --include-org-settings \
  --backup-file my_switch_backup.json
```

## Helper Features for Device Migration

### Generate Inventory Report
Get a detailed report of all devices before migration:
```bash
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --mode inventory \
  --source-org SOURCE_ORG_ID \
  --source-network SOURCE_NETWORK_ID
```

This creates:
- JSON report with full device details
- CSV file for easy reference
- Summary of device models and counts

### Verify Devices in Target Organization
Check which devices have been successfully claimed:
```bash
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --mode verify \
  --backup-file my_switch_backup.json \
  --target-org TARGET_ORG_ID
```

### Prepare Devices for Migration
The prepare mode helps you update device notes with claim information BEFORE migration:

#### Generate Claim Info Template
```bash
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --mode prepare \
  --source-network SOURCE_NETWORK_ID
```

This creates a template file with all your devices. Edit it to add order numbers:

```json
{
  "Q2XX-XXXX-XXX1": {
    "name": "Main Switch",
    "model": "MS120-48LP",
    "order": "1234-ABCD-5678",
    "claim": "OR_ENTER_CLAIM_KEY"
  }
}
```

#### Update Device Notes Automatically
```bash
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --mode prepare \
  --source-network SOURCE_NETWORK_ID \
  --claim-info claim_info_template.json
```

This adds order/claim information to each device's notes field.

#### Tag Devices for Migration
```bash
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --mode prepare \
  --source-network SOURCE_NETWORK_ID \
  --add-tag "migration-batch-1"
```

#### Do Both at Once
```bash
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --mode prepare \
  --source-network SOURCE_NETWORK_ID \
  --claim-info claim_info.json \
  --add-tag "migration-ready"
```

### Generate Migration Checklist
Create a detailed checklist from your backup:
```bash
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --generate-checklist \
  --backup-file my_switch_backup.json
```

This creates:
- JSON checklist with device details
- Text checklist for printing/reference
- Step-by-step migration instructions
- Claim information (if found in notes/tags)

### Restore to a New Network
```bash
# Without device mapping (network settings only)
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --mode restore \
  --backup-file my_switch_backup.json \
  --target-org TARGET_ORG_ID

# With device mapping (includes port configurations)
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --mode restore \
  --backup-file my_switch_backup.json \
  --target-org TARGET_ORG_ID \
  --device-mapping my_switch_backup_device_mapping.json
```

### Direct Migration
```bash
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --mode migrate \
  --source-org SOURCE_ORG_ID \
  --source-network SOURCE_NETWORK_ID \
  --target-org TARGET_ORG_ID \
  --include-org-settings
```

## Recommended Migration Workflow

### Step 1: Create Inventory Report
```bash
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --mode inventory \
  --source-org SOURCE_ORG_ID \
  --source-network SOURCE_NETWORK_ID
```

### Step 2: Prepare Devices (Add Claim Info to Notes)
```bash
# Generate template
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --mode prepare \
  --source-network SOURCE_NETWORK_ID

# Edit the generated claim_info_template_*.json file with order numbers

# Apply the claim information to device notes
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --mode prepare \
  --source-network SOURCE_NETWORK_ID \
  --claim-info claim_info_template_*.json \
  --add-tag "migration-ready"
```

### Step 3: Backup Network Configuration
```bash
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --mode backup \
  --source-org SOURCE_ORG_ID \
  --source-network SOURCE_NETWORK_ID \
  --include-org-settings \
  --backup-file switch_migration.json
```

This automatically generates:
- `switch_migration.json` - Complete backup
- `switch_migration_device_mapping.json` - Device mapping template
- `switch_migration_checklist.json` - Migration checklist (with claim info from notes!)
- `switch_migration_checklist.txt` - Printable checklist

### Step 4: Review Migration Checklist
Open the text checklist to see:
- List of all devices to migrate
- Serial numbers and models
- Any claim information found
- Step-by-step instructions

### Step 4: Release Devices from Source Org
1. Log into source organization Dashboard
2. Go to Organization > Inventory
3. Select all switches from your checklist
4. Click "Remove from organization"

### Step 5: Claim Devices in Target Org
1. Log into target organization Dashboard
2. Go to Organization > Inventory > Claim
3. Enter serial numbers or order numbers
4. Claim all devices

### Step 6: Create Target Network (if needed)
```bash
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --mode restore \
  --backup-file switch_migration.json \
  --target-org TARGET_ORG_ID
```
Note: This creates the network but won't restore device configs yet.

### Step 7: Add Devices to Network
In the Dashboard:
1. Go to your new network
2. Navigate to Switches > Add switches
3. Select all claimed switches
4. Add to network

### Step 8: Verify All Devices Are Ready
```bash
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --mode verify \
  --backup-file switch_migration.json \
  --target-org TARGET_ORG_ID
```

Or wait for them to appear:
```bash
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --mode wait \
  --backup-file switch_migration.json \
  --target-org TARGET_ORG_ID \
  --target-network TARGET_NETWORK_ID
```

### Step 9: Update Device Mapping (if needed)
If any serial numbers changed during the claim process:
1. Edit `switch_migration_device_mapping.json`
2. Replace "ENTER_NEW_SERIAL_HERE" with actual new serials

### Step 10: Restore Full Configuration
```bash
python meraki_migration.py \
  --api-key YOUR_API_KEY \
  --mode restore \
  --backup-file switch_migration.json \
  --target-org TARGET_ORG_ID \
  --target-network TARGET_NETWORK_ID \
  --device-mapping switch_migration_device_mapping.json
```

## What Gets Migrated

### ✅ Switch-Specific Settings

**Port Configurations**:
- Access/trunk mode settings
- VLAN assignments (access VLAN, allowed VLANs, native VLAN)
- Voice VLAN settings
- PoE enabled/disabled and power limits
- Port isolation
- STP guard settings (BPDU, root, loop guard)
- Storm control percentages
- Port schedules
- Speed/duplex settings
- UDLD settings

**Network Settings**:
- Global switch settings
- RADIUS/802.1X configurations
- Access control lists
- DHCP server policies
- QoS and DSCP mappings
- MTU configurations
- STP priorities and settings
- Multicast and IGMP snooping
- Port mirroring
- Link aggregations

**Organization Settings** (when included):
- Adaptive policy configurations
- Configuration templates
- Policy objects
- SAML configurations

### ❌ Not Migrated
- Switch hardware (must be reclaimed)
- Historical data and analytics
- Client-specific settings
- Current port status/statistics
- MAC address tables
- Active DHCP leases
- Spanning tree topology state

## Backup File Structure

```json
{
  "timestamp": "2024-01-01T12:00:00",
  "org_id": "source_org_id",
  "network_id": "source_network_id",
  "network_info": { 
    "name": "Switch Network",
    "productTypes": ["switch"],
    ...
  },
  "devices": [
    {
      "serial": "Q2XX-XXXX-XXXX",
      "name": "Main Switch",
      "model": "MS120-48LP",
      "configurations": {
        "switchPorts": [
          {
            "portId": "1",
            "name": "Uplink",
            "type": "trunk",
            "vlan": 1,
            "allowedVlans": "all",
            "poeEnabled": false,
            ...
          }
        ],
        "management": { ... }
      }
    }
  ],
  "switch_settings": {
    "settings": { ... },
    "accessPolicies": [ ... ],
    "qosRules": [ ... ],
    ...
  },
  "settings": {
    "alerts": { ... },
    "groupPolicies": [ ... ],
    ...
  },
  "org_settings": {
    "adaptivePolicy": { ... },
    "configTemplates": [ ... ],
    ...
  }
}
```

## Claim Info Template Format

When using prepare mode, the claim info JSON should follow this format:

```json
{
  "Q2XX-XXXX-OLD1": {
    "name": "Main Switch",
    "model": "MS120-48LP",
    "order": "1234-ABCD-5678",
    "claim": "XXXX-XXXX-XXXX"
  },
  "Q2XX-XXXX-OLD2": "Order: 9876-ZYXW-4321"
}
```

You can use either:
- A simple string value: `"serial": "Order: 1234-ABCD-5678"`
- An object with fields: `"serial": {"order": "1234-ABCD-5678"}`

## Device Mapping File

The device mapping file helps restore port configurations to the correct switches:

```json
{
  "Q2XX-XXXX-OLD1": {
    "old_serial": "Q2XX-XXXX-OLD1",
    "old_name": "Main Switch",
    "old_model": "MS120-48LP",
    "new_serial": "Q2XX-XXXX-NEW1"
  },
  "Q2XX-XXXX-OLD2": {
    "old_serial": "Q2XX-XXXX-OLD2",
    "old_name": "Access Switch 1",
    "old_model": "MS120-24P",
    "new_serial": "Q2XX-XXXX-NEW2"
  }
}
```

## Troubleshooting

### Common Issues

**Port Configuration Not Restoring**:
- Ensure switches are claimed and added to the network
- Verify device mapping file has correct serial numbers
- Check that switch models are compatible

**Access Policy Errors**:
- RADIUS servers must be configured first
- Ensure authentication settings match capabilities

**VLAN Issues**:
- VLANs referenced in port configs must exist
- Check VLAN ID conflicts with existing networks

**Stack Configuration**:
- Stack members must be physically connected
- All stack members must be in the network

## Best Practices

1. **Test First**: Always test with a small network before migrating production
2. **Verify Models**: Ensure target switches support all features being migrated
3. **Plan Downtime**: Switch migration requires physical reclaiming
4. **Document Mapping**: Keep clear records of old-to-new serial mappings
5. **Backup Regularly**: Keep backups before making changes

### Pro Tip: Automatically Store Claim Information
Before migration, use the prepare mode to automatically add order numbers or claim keys to device notes:

1. Generate the template: `--mode prepare --source-network NETWORK_ID`
2. Edit the template with your order numbers
3. Apply it: `--mode prepare --source-network NETWORK_ID --claim-info your_file.json`

The script will automatically extract this information during backup!

## Migration Checklist Details

The auto-generated migration checklist includes:

1. **Device Information**:
   - Serial numbers
   - Device names and models
   - MAC addresses
   - Port counts
   - Tags and notes
   - **Claim information** (automatically extracted from device notes)

2. **Migration Steps**:
   - Clear instructions for removing devices
   - How to claim in new organization
   - Network setup steps
   - Configuration restore process

3. **Claim Information Sources**:
   The script extracts claim info from device notes using patterns like:
   - `Order: 1234-ABCD-5678`
   - `order#1234-ABCD-5678`
   - `claim: XXXX-XXXX-XXXX`
   - `Claim-XXXX-XXXX-XXXX`

   Use the **prepare mode** to automatically add this information before migration!

## Security Considerations

1. **API Keys**: Never commit to version control
2. **Backup Files**: Contain sensitive network configurations
3. **Access Control**: Limit who can access backup files
4. **Encryption**: Consider encrypting backup files at rest

## Example Outputs

### Prepare Mode - Update Device Notes
```
Preparing devices for migration in network L_123456789012345678

✓ Updated notes for 12/12 devices
✓ Tagged 12/12 devices with 'migration-ready'
```

### Prepare Mode - Generate Template
```
✓ Generated claim info template: claim_info_template_L_123456789012345678.json

To use this template:
1. Edit the file and add order numbers or claim keys
2. Run: python meraki_migration.py --api-key KEY --mode prepare \
        --source-network L_123456789012345678 --claim-info claim_info_template_L_123456789012345678.json
```

### Inventory Report
```
✓ Inventory report generated!
  - JSON report: inventory_L_123456_20240115_143022.json
  - CSV report: inventory_L_123456_20240115_143022.csv

Summary:
  - Total devices: 12
  - Device models:
    - MS120-48LP: 8
    - MS120-24P: 3
    - MS250-48FP: 1
```

### Backup with Auto-Generated Files
```
✓ Backup complete!
  - Backup file: meraki_backup_L_123456_20240115_143022.json
  - Device mapping: meraki_backup_L_123456_20240115_143022_device_mapping.json
  - Migration checklist: meraki_backup_L_123456_20240115_143022_checklist.json
  - Text checklist: meraki_backup_L_123456_20240115_143022_checklist.txt

Total devices to migrate: 12

Next steps:
1. Review the migration checklist
2. Remove devices from source organization
3. Claim devices in target organization
4. Update device mapping if serials changed
5. Run restore with --device-mapping
```

### Device Verification
```
Verifying devices in target organization...

✓ Found in target org (10):
  - Q2XX-XXXX-XXX1 (Main Switch)
  - Q2XX-XXXX-XXX2 (Access Switch 1)
  - Q2XX-XXXX-XXX3 (Access Switch 2)
  ...

✗ Missing from target org (2):
  - Q2XX-XXXX-XXX11 (IDF Switch 1)
  - Q2XX-XXXX-XXX12 (IDF Switch 2)
```

### Device Wait Monitoring
```
Waiting for 12 devices to appear in target organization...
Timeout: 300 seconds
Press Ctrl+C to stop waiting

✓ Device Q2XX-XXXX-XXX1 found in organization inventory
✓ Device Q2XX-XXXX-XXX2 found in organization inventory
Still waiting for 10 devices: Q2XX-XXXX-XXX3, Q2XX-XXXX-XXX4, ...
✓ Device Q2XX-XXXX-XXX3 found in organization inventory
✓ Device Q2XX-XXXX-XXX3 added to network
...
All devices successfully added to network!

✓ All devices are ready for configuration restore!
  Network ID: L_123456789012345678
  
You can now run restore with --device-mapping
```

### Device Wait Monitoring
```
Waiting for 12 devices to appear in target organization...
Timeout: 300 seconds
Press Ctrl+C to stop waiting

✓ Device Q2XX-XXXX-XXX1 found in organization inventory
✓ Device Q2XX-XXXX-XXX2 found in organization inventory
Still waiting for 10 devices: Q2XX-XXXX-XXX3, Q2XX-XXXX-XXX4, ...
✓ Device Q2XX-XXXX-XXX3 found in organization inventory
✓ Device Q2XX-XXXX-XXX3 added to network
...
All devices successfully added to network!

✓ All devices are ready!
  All devices added to network: L_123456789012345678
  
You can now run restore with --device-mapping
```

## Generated Files Summary

When you run a backup, the script automatically creates these files:

| File | Purpose | Contents |
|------|---------|----------|
| `*_backup.json` | Main backup file | All network/device configurations |
| `*_device_mapping.json` | Serial number mapping | Maps old serials to new ones |
| `*_checklist.json` | Migration checklist (JSON) | Structured migration data |
| `*_checklist.txt` | Migration checklist (text) | Human-readable instructions |

When you run inventory mode:

| File | Purpose | Contents |
|------|---------|----------|
| `*_inventory.json` | Detailed inventory | Full device details, IPs, uplinks |
| `*_inventory.csv` | Simple inventory | Serial, name, model, MAC for reference |

All files include timestamps in their names to prevent overwrites.

## Support

For issues with:
- The script: Check log files in the same directory
- Meraki API: [Meraki API Documentation](https://developer.cisco.com/meraki/api-v1/)
- Switch features: Contact Meraki support

## Version Requirements

- Meraki API v1
- Python 3.6+
- Active Meraki organization administrator access
- Appropriate licensing for all features being migrated
