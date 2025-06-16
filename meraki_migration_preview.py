#!/usr/bin/env python3
"""
Meraki Migration Dry Run Tool
Preview what will be migrated without making any changes
"""

import json
import argparse
from datetime import datetime
from meraki_auto_migration import MerakiAPIClient, ComprehensiveBackup
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def generate_migration_preview(api_key: str, source_org_id: str, source_network_id: str, target_org_id: str):
    """Generate a detailed preview of what will be migrated"""
    
    api = MerakiAPIClient(api_key)
    backup_tool = ComprehensiveBackup(api)
    
    # Get organization names
    source_org_name = api.get_org_name(source_org_id)
    target_org_name = api.get_org_name(target_org_id)
    
    # Get network info
    network_info = api.get_network_info(source_network_id)
    
    # Get devices
    devices = api.get_devices(source_network_id)
    
    # Create preview report
    preview = {
        "generated_at": datetime.now().isoformat(),
        "migration_summary": {
            "source_org": {
                "id": source_org_id,
                "name": source_org_name
            },
            "target_org": {
                "id": target_org_id,
                "name": target_org_name
            },
            "network": {
                "id": source_network_id,
                "name": network_info.get("name"),
                "timezone": network_info.get("timeZone"),
                "product_types": network_info.get("productTypes", [])
            },
            "devices_count": len(devices),
            "total_ports": sum(int(d.get('model', '').split('-')[-1].rstrip('LP').rstrip('P')) 
                             for d in devices if 'MS' in d.get('model', '') and '-' in d.get('model', ''))
        },
        "devices_to_migrate": [],
        "settings_to_migrate": {
            "network_level": [],
            "device_level": []
        },
        "migration_steps": [],
        "estimated_duration": ""
    }
    
    # Device details
    for device in devices:
        device_info = {
            "serial": device['serial'],
            "name": device.get('name', 'Unnamed'),
            "model": device.get('model', ''),
            "mac": device.get('mac', ''),
            "current_ip": device.get('lanIp', 'DHCP'),
            "firmware": device.get('firmware', ''),
            "status": "Will be unclaimed and reclaimed"
        }
        preview["devices_to_migrate"].append(device_info)
    
    # Settings that will be migrated
    network_settings = [
        "STP (Spanning Tree Protocol) configuration",
        "MTU (Maximum Transmission Unit) settings",
        "Access Control Lists (ACLs)",
        "802.1X and MAB access policies",
        "SNMP v2/v3 configuration",
        "QoS rules and DSCP mappings",
        "Port schedules",
        "Storm control settings",
        "DHCP server policies",
        "Link aggregations (LACP)",
        "Routing configuration (OSPF, static routes)",
        "Multicast settings",
        "Syslog servers",
        "NetFlow collectors",
        "Alert settings"
    ]
    preview["settings_to_migrate"]["network_level"] = network_settings
    
    device_settings = [
        "All port configurations (access/trunk, VLANs, PoE)",
        "Port names and descriptions",
        "Management interface settings (IP, VLAN)",
        "Layer 3 interfaces (if applicable)",
        "Static routes per device",
        "DHCP server configuration"
    ]
    preview["settings_to_migrate"]["device_level"] = device_settings
    
    # Migration steps
    steps = [
        {
            "step": 1,
            "action": "Backup Configuration",
            "description": "Save all network and device settings",
            "duration": "1-2 minutes",
            "automated": True
        },
        {
            "step": 2,
            "action": "Unclaim Devices",
            "description": f"Remove {len(devices)} devices from {source_org_name}",
            "duration": "1-2 minutes",
            "automated": True
        },
        {
            "step": 3,
            "action": "Wait Period",
            "description": "Required 120-second wait for Meraki processing",
            "duration": "2 minutes",
            "automated": True
        },
        {
            "step": 4,
            "action": "Claim Devices",
            "description": f"Add {len(devices)} devices to {target_org_name}",
            "duration": "1-2 minutes",
            "automated": True
        },
        {
            "step": 5,
            "action": "Create Network",
            "description": f"Create new network in {target_org_name}",
            "duration": "10 seconds",
            "automated": True
        },
        {
            "step": 6,
            "action": "Add Devices to Network",
            "description": "Associate devices with new network",
            "duration": "30 seconds",
            "automated": True
        },
        {
            "step": 7,
            "action": "Restore Configuration",
            "description": "Apply all saved settings",
            "duration": "2-5 minutes",
            "automated": True
        }
    ]
    preview["migration_steps"] = steps
    
    # Calculate estimated duration
    total_devices = len(devices)
    estimated_minutes = 8 + (total_devices // 10)  # Base 8 minutes + 1 minute per 10 devices
    preview["estimated_duration"] = f"{estimated_minutes}-{estimated_minutes + 5} minutes"
    
    return preview


def print_preview(preview: Dict):
    """Print a formatted preview"""
    print("\n" + "=" * 70)
    print("MERAKI NETWORK MIGRATION DRY RUN")
    print("=" * 70)
    
    print(f"\nGenerated: {preview['generated_at']}")
    
    print("\n### MIGRATION SUMMARY ###")
    summary = preview['migration_summary']
    print(f"Source Organization: {summary['source_org']['name']} (ID: {summary['source_org']['id']})")
    print(f"Target Organization: {summary['target_org']['name']} (ID: {summary['target_org']['id']})")
    print(f"Network Name: {summary['network']['name']}")
    print(f"Network ID: {summary['network']['id']}")
    print(f"Product Types: {', '.join(summary['network']['product_types'])}")
    print(f"Devices to Migrate: {summary['devices_count']}")
    print(f"Total Switch Ports: {summary['total_ports']}")
    
    print("\n### DEVICES TO MIGRATE ###")
    for device in preview['devices_to_migrate']:
        print(f"\n- Serial: {device['serial']}")
        print(f"  Name: {device['name']}")
        print(f"  Model: {device['model']}")
        print(f"  Current IP: {device['current_ip']}")
        print(f"  Status: {device['status']}")
    
    print("\n### SETTINGS TO MIGRATE ###")
    print("\nNetwork-Level Settings:")
    for setting in preview['settings_to_migrate']['network_level']:
        print(f"  ✓ {setting}")
    
    print("\nDevice-Level Settings:")
    for setting in preview['settings_to_migrate']['device_level']:
        print(f"  ✓ {setting}")
    
    print("\n### MIGRATION PROCESS ###")
    for step in preview['migration_steps']:
        print(f"\nStep {step['step']}: {step['action']}")
        print(f"  Description: {step['description']}")
        print(f"  Duration: {step['duration']}")
        print(f"  Automated: {'Yes' if step['automated'] else 'No'}")
    
    print(f"\n### ESTIMATED TOTAL DURATION: {preview['estimated_duration']} ###")
    
    print("\n### IMPORTANT NOTES ###")
    print("- Devices will be temporarily offline during unclaim/claim process")
    print("- All settings will be preserved and restored")
    print("- Historical data and client information will not be migrated")
    print("- The migration is fully automated using UI automation")
    print("- THIS IS A DRY RUN - No changes will be made")
    
    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Meraki migration dry run - Preview without making changes")
    parser.add_argument("--api-key", required=True, help="Meraki API key")
    parser.add_argument("--source-org", required=True, help="Source organization ID")
    parser.add_argument("--source-network", required=True, help="Source network ID")
    parser.add_argument("--target-org", required=True, help="Target organization ID")
    parser.add_argument("--save-preview", help="Save preview to JSON file")
    
    args = parser.parse_args()
    
    try:
        print("\nRunning migration dry run (no changes will be made)...")
        
        preview = generate_migration_preview(
            args.api_key,
            args.source_org,
            args.source_network,
            args.target_org
        )
        
        # Print preview
        print_preview(preview)
        
        # Save if requested
        if args.save_preview:
            with open(args.save_preview, 'w') as f:
                json.dump(preview, f, indent=2)
            print(f"\nDry run results saved to: {args.save_preview}")
        
        print("\nTo proceed with actual migration, use:")
        print("  python meraki_migration.py (with environment variables)")
        print("  or")
        print("  python meraki_auto_migration.py (with inline credentials)")
        
    except Exception as e:
        logger.error(f"Failed to generate preview: {e}")
        print(f"\n✗ Failed to generate preview: {e}")


if __name__ == "__main__":
    main()
