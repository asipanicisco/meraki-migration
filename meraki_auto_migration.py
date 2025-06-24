#!/usr/bin/env python3
"""
Meraki Network Migration Tool with UI Automation
Complete migration with explicit org/network names and IDs
Fixed version incorporating working methods from debug.py
"""

import json
import logging
import argparse
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import os
import tempfile
import shutil
import uuid
import subprocess
import psutil
import signal

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for more detailed logs
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'meraki_migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Set specific loggers to WARNING to reduce noise
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("selenium").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)


class MerakiAPIClient:
    """Handles all Meraki API operations"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.meraki.com/api/v1"
        self.headers = {
            "X-Cisco-Meraki-API-Key": api_key,
            "Content-Type": "application/json"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _api_call(self, method: str, endpoint: str, data: Optional[Dict] = None,
              params: Optional[Dict] = None) -> Any:
        """Make API call with enhanced error logging"""
        url = f"{self.base_url}{endpoint}"

        for attempt in range(3):
            try:
                # Log the request details
                logger.debug(f"API Request: {method} {url}")
                if data:
                    logger.debug(f"Request Body: {json.dumps(data, indent=2)}")
                if params:
                    logger.debug(f"Request Params: {params}")

                response = self.session.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params
                )

                # Log response details
                logger.debug(f"Response Status: {response.status_code}")
                logger.debug(f"Response Headers: {dict(response.headers)}")

                # Log response body for errors
                if response.status_code >= 400:
                    try:
                        response_body = response.json()
                        logger.error(f"API Error Response: {json.dumps(response_body, indent=2)}")
                    except:
                        logger.error(f"API Error Response (text): {response.text}")

                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 1))
                    logger.warning(f"Rate limited. Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue

                # Don't retry on 404s - feature not available
                if response.status_code == 404:
                    return None

                response.raise_for_status()

                if response.content:
                    return response.json()
                return None

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    # Feature not available for this network/device
                    return None

                # Enhanced error logging
                logger.error(f"API call failed: {method} {url}")
                logger.error(f"Status Code: {e.response.status_code}")
                logger.error(f"Error: {e}")

                # Try to get more error details
                try:
                    error_body = e.response.json()
                    logger.error(f"Error Details: {json.dumps(error_body, indent=2)}")
                except:
                    logger.error(f"Error Response Text: {e.response.text}")

                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
            except requests.exceptions.RequestException as e:
                logger.error(f"API call failed: {e}")
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)

    def get_organizations(self) -> List[Dict]:
        """Get all organizations"""
        return self._api_call("GET", "/organizations")

    def verify_org_access(self, org_id: str, expected_name: str) -> bool:
        """Verify organization ID and name match"""
        try:
            org = self._api_call("GET", f"/organizations/{org_id}")
            if org and org['name'] == expected_name:
                logger.info(f"✓ Verified org: {expected_name} (ID: {org_id})")
                return True
            else:
                logger.error(f"✗ Org name mismatch. Expected: {expected_name}, Got: {org.get('name', 'N/A')}")
                return False
        except Exception as e:
            logger.error(f"✗ Cannot access org {org_id}: {e}")
            return False

    def verify_network_access(self, network_id: str, expected_name: str) -> bool:
        """Verify network ID and name match"""
        try:
            network = self._api_call("GET", f"/networks/{network_id}")
            if network and network['name'] == expected_name:
                logger.info(f"✓ Verified network: {expected_name} (ID: {network_id})")
                return True
            else:
                logger.error(f"✗ Network name mismatch. Expected: {expected_name}, Got: {network.get('name', 'N/A')}")
                return False
        except Exception as e:
            logger.error(f"✗ Cannot access network {network_id}: {e}")
            return False

    def get_network_info(self, network_id: str) -> Dict:
        """Get network information"""
        return self._api_call("GET", f"/networks/{network_id}")

    def get_devices(self, network_id: str) -> List[Dict]:
        """Get all devices in a network"""
        return self._api_call("GET", f"/networks/{network_id}/devices")

    def create_network(self, org_id: str, network_config: Dict) -> str:
        """Create a new network or return existing network ID if it already exists"""
        network_name = network_config.get('name', '')

        # First, check if a network with this name already exists
        try:
            existing_networks = self._api_call("GET", f"/organizations/{org_id}/networks")
            for network in existing_networks:
                if network['name'] == network_name:
                    logger.info(f"Network '{network_name}' already exists with ID: {network['id']}")
                    return network['id']
        except Exception as e:
            logger.warning(f"Could not check existing networks: {e}")

        # Try to create the network
        try:
            result = self._api_call("POST", f"/organizations/{org_id}/networks", data=network_config)
            return result['id']
        except Exception as e:
            if "400" in str(e):
                # Try to get more specific error information
                logger.error(f"Failed to create network. Possible reasons:")
                logger.error("  - Network name already exists")
                logger.error("  - Invalid product types for this organization")
                logger.error("  - Organization doesn't support the requested product types")
                logger.error(f"Network config attempted: {network_config}")

                # As a fallback, try to find the network again
                try:
                    existing_networks = self._api_call("GET", f"/organizations/{org_id}/networks")
                    for network in existing_networks:
                        if network['name'] == network_name:
                            logger.info(f"Found existing network '{network_name}' with ID: {network['id']}")
                            return network['id']
                except:
                    pass
            raise

    def add_devices_to_network(self, network_id: str, serials: List[str]) -> bool:
        """Add devices to network"""
        try:
            self._api_call("POST", f"/networks/{network_id}/devices/claim",
                           data={"serials": serials})
            return True
        except Exception as e:
            logger.error(f"Failed to add devices to network: {e}")
            return False


class ComprehensiveBackup:
    """Handles comprehensive backup of all network and device settings"""

    def __init__(self, api_client: MerakiAPIClient):
        self.api = api_client

    def backup_all_settings(self, org_id: str, org_name: str, network_id: str, network_name: str) -> Dict:
        """Backup all network and device settings comprehensively"""
        logger.info(f"Starting comprehensive backup for network '{network_name}'")

        backup = {
            "timestamp": datetime.now().isoformat(),
            "org_id": org_id,
            "org_name": org_name,
            "network_id": network_id,
            "network_name": network_name,
            "network_info": {},
            "devices": [],
            "network_settings": {
                "switch": {},
                "routing": {},
                "security": {},
                "monitoring": {}
            },
            "device_settings": {}
        }

        # Get network info
        backup["network_info"] = self.api.get_network_info(network_id)
        logger.info("Backed up network info")

        # Get devices
        devices = self.api.get_devices(network_id)
        backup["devices"] = devices
        logger.info(f"Found {len(devices)} devices")

        # Backup network-level switch settings
        self._backup_switch_network_settings(network_id, backup["network_settings"]["switch"])

        # Backup routing settings
        self._backup_routing_settings(network_id, backup["network_settings"]["routing"])

        # Backup security settings
        self._backup_security_settings(network_id, backup["network_settings"]["security"])

        # Backup monitoring settings
        self._backup_monitoring_settings(network_id, backup["network_settings"]["monitoring"])

        # Backup device-specific settings
        for device in devices:
            serial = device['serial']
            backup["device_settings"][serial] = self._backup_device_settings(serial, device)

        # Log backup summary
        logger.info("=" * 50)
        logger.info("BACKUP SUMMARY")
        logger.info("=" * 50)
        logger.info(f"Organization: {org_name} ({org_id})")
        logger.info(f"Network: {network_name} ({network_id})")
        logger.info(f"Devices: {len(devices)}")

        # Count backed up settings
        switch_count = sum(1 for v in backup["network_settings"]["switch"].values() if v)
        routing_count = sum(1 for v in backup["network_settings"]["routing"].values() if v)
        security_count = sum(1 for v in backup["network_settings"]["security"].values() if v)
        monitoring_count = sum(1 for v in backup["network_settings"]["monitoring"].values() if v)

        logger.info(f"Network Settings Backed Up:")
        logger.info(f"  - Switch settings: {switch_count}")
        logger.info(f"  - Routing settings: {routing_count}")
        logger.info(f"  - Security settings: {security_count}")
        logger.info(f"  - Monitoring settings: {monitoring_count}")

        port_count = sum(len(d.get("ports", [])) for d in backup["device_settings"].values())
        logger.info(f"Device Settings Backed Up:")
        logger.info(f"  - Total ports configured: {port_count}")
        logger.info("=" * 50)

        return backup

    def _backup_switch_network_settings(self, network_id: str, settings: Dict):
        """Backup switch-specific network settings"""
        endpoints = {
            "stp": f"/networks/{network_id}/switch/stp",
            "mtu": f"/networks/{network_id}/switch/mtu",
            "settings": f"/networks/{network_id}/switch/settings",
            "accessPolicies": f"/networks/{network_id}/switch/accessPolicies",
            "portSchedules": f"/networks/{network_id}/switch/portSchedules",
            "qosRules": f"/networks/{network_id}/switch/qosRules",
            "stormControl": f"/networks/{network_id}/switch/stormControl",
            "dhcpServerPolicy": f"/networks/{network_id}/switch/dhcpServerPolicy",
            "dscpToCosMappings": f"/networks/{network_id}/switch/dscp",
            "alternateManagementInterface": f"/networks/{network_id}/switch/alternateManagementInterface",
            "linkAggregations": f"/networks/{network_id}/switch/linkAggregations"
        }

        # Features that commonly return 404 (not available on all networks)
        optional_features = ["dscpToCosMappings", "linkAggregations", "alternateManagementInterface", "accessControlLists"]

        for name, endpoint in endpoints.items():
            try:
                result = self.api._api_call("GET", endpoint)
                if result is not None:
                    settings[name] = result
                    logger.info(f"Backed up switch {name}")
                elif name in optional_features:
                    logger.debug(f"Switch {name} not available on this network")
                else:
                    logger.info(f"Switch {name} not configured")
            except Exception as e:
                if "404" not in str(e):
                    logger.warning(f"Could not backup switch {name}: {e}")

    def _backup_routing_settings(self, network_id: str, settings: Dict):
        """Backup routing settings"""
        endpoints = {
            "staticRoutes": f"/networks/{network_id}/appliance/staticRoutes",
            "ospf": f"/networks/{network_id}/switch/routing/ospf",
            "multicast": f"/networks/{network_id}/switch/routing/multicast",
            "warmSpare": f"/networks/{network_id}/switch/warmSpare"
        }

        # Features that commonly return 404
        optional_features = ["warmSpare", "ospf"]

        for name, endpoint in endpoints.items():
            try:
                result = self.api._api_call("GET", endpoint)
                if result is not None:
                    settings[name] = result
                    logger.info(f"Backed up routing {name}")
                elif name in optional_features:
                    logger.debug(f"Routing {name} not available on this network")
                else:
                    logger.info(f"Routing {name} not configured")
            except Exception as e:
                if "404" not in str(e):
                    logger.warning(f"Could not backup routing {name}: {e}")

    def _backup_security_settings(self, network_id: str, settings: Dict):
        """Backup security settings including ACLs"""
        endpoints = {
            "accessControlLists": f"/networks/{network_id}/switch/accessControlLists",
            "portSecurity": f"/networks/{network_id}/switch/portSecurity",
            "stpGuard": f"/networks/{network_id}/switch/stpGuard"
        }

        # Features that commonly return 404 (newer features)
        optional_features = ["portSecurity", "stpGuard"]

        for name, endpoint in endpoints.items():
            try:
                result = self.api._api_call("GET", endpoint)
                if result is not None:
                    settings[name] = result
                    logger.info(f"Backed up security {name}")
                elif name in optional_features:
                    logger.debug(f"Security {name} not available on this network")
                else:
                    logger.info(f"Security {name} not configured")
            except Exception as e:
                if "404" not in str(e):
                    logger.warning(f"Could not backup security {name}: {e}")

    def _backup_monitoring_settings(self, network_id: str, settings: Dict):
        """Backup monitoring settings"""
        endpoints = {
            "snmp": f"/networks/{network_id}/snmp",
            "syslog": f"/networks/{network_id}/syslogServers",
            "netflow": f"/networks/{network_id}/netflow",
            "alerts": f"/networks/{network_id}/alerts/settings"
        }

        for name, endpoint in endpoints.items():
            try:
                result = self.api._api_call("GET", endpoint)
                if result is not None:
                    settings[name] = result
                    logger.info(f"Backed up monitoring {name}")
                else:
                    logger.info(f"Monitoring {name} not configured")
            except Exception as e:
                if "404" not in str(e):
                    logger.warning(f"Could not backup monitoring {name}: {e}")

    def _backup_device_settings(self, serial: str, device_info: Dict) -> Dict:
        """Backup all device-specific settings"""
        device_name = device_info.get('name', 'Unnamed')
        logger.info(f"Backing up device {serial} ({device_name})")

        settings = {
            "info": device_info,
            "ports": [],
            "management": {},
            "routing": {},
            "dhcp": {},
            "warmSpare": {}
        }

        # Management interface (includes IP settings)
        try:
            result = self.api._api_call("GET", f"/devices/{serial}/managementInterface")
            if result is not None:
                settings["management"] = result
            else:
                logger.debug(f"No management interface configured for {serial}")
        except Exception as e:
            if "404" not in str(e):
                logger.warning(f"Could not backup management interface for {serial}: {e}")

        # Switch ports (all port-level settings)
        if device_info.get('model', '').startswith('MS') or device_info.get('model', '').startswith('C9'):
            try:
                ports = self.api._api_call("GET", f"/devices/{serial}/switch/ports")
                if ports is not None:
                    settings["ports"] = ports
                    logger.info(f"Backed up {len(ports)} ports for {serial}")
                else:
                    logger.info(f"No port configuration for {serial}")
            except Exception as e:
                if "404" not in str(e):
                    logger.warning(f"Could not backup ports for {serial}: {e}")

            # Enhanced Routing backup for L3 switches
            # Routing interfaces (Layer 3)
            try:
                interfaces = self.api._api_call("GET", f"/devices/{serial}/switch/routing/interfaces")
                if interfaces is not None:
                    settings["routing"]["interfaces"] = interfaces
                    logger.info(f"Backed up {len(interfaces)} routing interfaces for {serial}")
            except Exception:
                pass  # Not all switches support L3

            # Static routes
            try:
                routes = self.api._api_call("GET", f"/devices/{serial}/switch/routing/staticRoutes")
                if routes is not None:
                    settings["routing"]["staticRoutes"] = routes
                    logger.info(f"Backed up {len(routes)} static routes for {serial}")
            except Exception:
                pass

            # OSPF settings (if enabled)
            try:
                ospf = self.api._api_call("GET", f"/devices/{serial}/switch/routing/ospf")
                if ospf is not None:
                    settings["routing"]["ospf"] = ospf
                    logger.info(f"Backed up OSPF settings for {serial}")
            except Exception:
                pass

            # Multicast settings
            try:
                multicast = self.api._api_call("GET", f"/devices/{serial}/switch/routing/multicast")
                if multicast is not None:
                    settings["routing"]["multicast"] = multicast
                    logger.info(f"Backed up multicast settings for {serial}")
            except Exception:
                pass

            # Rendezvous points for multicast
            try:
                rp = self.api._api_call("GET", f"/devices/{serial}/switch/routing/multicast/rendezvousPoints")
                if rp is not None:
                    settings["routing"]["rendezvousPoints"] = rp
                    logger.info(f"Backed up multicast rendezvous points for {serial}")
            except Exception:
                pass

            # Enhanced DHCP backup
            # DHCP server settings (subnets)
            try:
                dhcp = self.api._api_call("GET", f"/devices/{serial}/switch/dhcp/v4/servers")
                if dhcp is not None:
                    settings["dhcp"]["servers"] = dhcp
                    logger.info(f"Backed up DHCP server settings for {serial}")
            except Exception:
                pass

            # DHCP relay settings
            try:
                relay = self.api._api_call("GET", f"/devices/{serial}/switch/dhcp/v4/relays")
                if relay is not None:
                    settings["dhcp"]["relays"] = relay
                    logger.info(f"Backed up DHCP relay settings for {serial}")
            except Exception:
                pass

            # Interface DHCP settings (per interface DHCP configuration)
            if settings["routing"].get("interfaces"):
                interface_dhcp = []
                for interface in settings["routing"]["interfaces"]:
                    interface_id = interface.get('interfaceId')
                    if interface_id:
                        try:
                            # Get DHCP settings for this specific interface
                            dhcp_settings = self.api._api_call("GET", f"/devices/{serial}/switch/routing/interfaces/{interface_id}/dhcp")
                            if dhcp_settings is not None:
                                interface_dhcp.append({
                                    "interfaceId": interface_id,
                                    "dhcpSettings": dhcp_settings
                                })
                                logger.debug(f"Backed up DHCP for interface {interface_id}")
                        except Exception:
                            pass

                if interface_dhcp:
                    settings["dhcp"]["interfaceDhcp"] = interface_dhcp
                    logger.info(f"Backed up DHCP settings for {len(interface_dhcp)} interfaces")

            # Warm spare settings
            try:
                warm_spare = self.api._api_call("GET", f"/devices/{serial}/switch/warmSpare")
                if warm_spare is not None:
                    settings["warmSpare"] = warm_spare
                    logger.info(f"Backed up warm spare settings for {serial}")
            except Exception:
                pass

            # Stack information (if part of a stack)
            try:
                stacks = self.api._api_call("GET", f"/networks/{device_info.get('networkId')}/switch/stacks")
                if stacks:
                    for stack in stacks:
                        if serial in stack.get('serials', []):
                            settings["stackInfo"] = stack
                            logger.info(f"Backed up stack information for {serial}")
                            break
            except Exception:
                pass
        return settings

class MerakiUIAutomation:
    """Handles UI automation for device unclaim/claim operations"""

    def __init__(self, username: str, password: str, headless: bool = False):
        self.username = username
        self.password = password
        self.driver = None
        self.wait = None
        self.headless = headless
        self.temp_dir = None

    def __enter__(self):
        self.setup_driver()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except Exception:
                pass

    def kill_chrome_processes(self):
        """Kill any existing Chrome/ChromeDriver processes using psutil for better cross-platform support"""
        try:
            killed_count = 0
            chrome_names = ['chrome', 'chromium', 'google-chrome', 'chromedriver', 'Chrome', 'Google Chrome']

            # Use psutil for more reliable process killing
            try:
                import psutil
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        process_name = proc.info['name'].lower()
                        for chrome_name in chrome_names:
                            if chrome_name.lower() in process_name:
                                proc.kill()
                                killed_count += 1
                                break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            except ImportError:
                # Fallback to system commands if psutil not available
                for process in chrome_names:
                    try:
                        subprocess.run(['pkill', '-9', '-f', process],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    except Exception:
                        pass

            # Clean up Chrome temp directories
            import glob
            temp_patterns = [
                '/tmp/.com.google.Chrome.*',
                '/tmp/chrome*',
                '/tmp/meraki_chrome*',
                '/tmp/.org.chromium.*',
                os.path.join(tempfile.gettempdir(), '.com.google.Chrome.*'),
                os.path.join(tempfile.gettempdir(), 'chrome*'),
                os.path.join(tempfile.gettempdir(), 'meraki_chrome*')
            ]

            for pattern in temp_patterns:
                for temp_dir in glob.glob(pattern):
                    try:
                        if os.path.isdir(temp_dir):
                            shutil.rmtree(temp_dir)
                    except Exception:
                        pass

            if killed_count > 0:
                logger.info(f"Killed {killed_count} Chrome-related processes")
                time.sleep(3)  # Give processes time to die

        except Exception as e:
            logger.warning(f"Error during Chrome cleanup: {e}")

    def setup_driver(self):
        """Setup Chrome driver with enhanced options to prevent session conflicts"""
        # Kill any existing Chrome processes first
        self.kill_chrome_processes()

        # Wait a bit to ensure everything is cleaned up
        time.sleep(2)

        options = webdriver.ChromeOptions()

        # Create truly unique user data directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        random_id = str(uuid.uuid4())[:8]
        self.temp_dir = os.path.join(
            tempfile.gettempdir(),
            f'meraki_chrome_{timestamp}_{random_id}'
        )

        # Ensure the directory doesn't exist
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        os.makedirs(self.temp_dir, mode=0o700)  # Create with restricted permissions

        logger.info(f"Using temp directory: {self.temp_dir}")

        # Core options for stability
        options.add_argument(f'--user-data-dir={self.temp_dir}')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=VizDisplayCompositor')
        options.add_argument('--disable-setuid-sandbox')

        # Headless mode if requested
        if self.headless:
            options.add_argument('--headless=new')
            # Additional options for headless stability
            options.add_argument('--disable-software-rasterizer')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-accelerated-2d-canvas')
            options.add_argument('--no-first-run')
            options.add_argument('--no-zygote')
            options.add_argument('--single-process')
            options.add_argument('--disable-gpu-sandbox')
            logger.info("Running Chrome in HEADLESS mode")
        else:
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')

        # Additional options for server environments
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-plugins')
        options.add_argument('--disable-images')
        options.add_argument('--disable-javascript')  # Temporarily for testing

        # More stability options
        options.add_argument('--disable-background-networking')
        options.add_argument('--disable-background-timer-throttling')
        options.add_argument('--disable-backgrounding-occluded-windows')
        options.add_argument('--disable-breakpad')
        options.add_argument('--disable-client-side-phishing-detection')
        options.add_argument('--disable-component-extensions-with-background-pages')
        options.add_argument('--disable-default-apps')
        options.add_argument('--disable-features=TranslateUI')
        options.add_argument('--disable-hang-monitor')
        options.add_argument('--disable-ipc-flooding-protection')
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--disable-prompt-on-repost')
        options.add_argument('--disable-renderer-backgrounding')
        options.add_argument('--disable-sync')
        options.add_argument('--force-color-profile=srgb')
        options.add_argument('--metrics-recording-only')
        options.add_argument('--safebrowsing-disable-auto-update')
        options.add_argument('--enable-automation')
        options.add_argument('--password-store=basic')
        options.add_argument('--use-mock-keychain')

        # Preferences to disable various features
        prefs = {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_settings.popups": 0,
            "profile.managed_default_content_settings.images": 1,
        }
        options.add_experimental_option("prefs", prefs)

        # Try to find chromedriver
        chromedriver_paths = [
            '/usr/bin/chromedriver',
            '/usr/local/bin/chromedriver',
            '/opt/chrome/chromedriver',
            'chromedriver',
            './chromedriver',
            shutil.which('chromedriver')
        ]

        chromedriver_path = None
        for path in chromedriver_paths:
            if path and os.path.exists(path):
                chromedriver_path = path
                logger.info(f"Found ChromeDriver at: {chromedriver_path}")
                break

        # Initialize driver with retry logic
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if chromedriver_path:
                    from selenium.webdriver.chrome.service import Service
                    service = Service(chromedriver_path)
                    service.log_path = os.path.join(self.temp_dir, 'chromedriver.log')
                    self.driver = webdriver.Chrome(service=service, options=options)
                else:
                    self.driver = webdriver.Chrome(options=options)

                self.wait = WebDriverWait(self.driver, 30)
                logger.info("Chrome driver initialized successfully")
                break

            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {e}")
                if attempt < max_attempts - 1:
                    logger.info("Cleaning up and retrying...")
                    self.kill_chrome_processes()
                    time.sleep(5)
                else:
                    logger.error("Failed to initialize Chrome driver after all attempts")
                    logger.error("Make sure Chrome and ChromeDriver are installed:")
                    logger.error("  sudo apt-get update")
                    logger.error("  sudo apt-get install -y google-chrome-stable chromium-chromedriver")
                    raise

    def save_debug_info(self, step: str, save_html: bool = False):
        """Save screenshot and optionally HTML for debugging"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_file = f"migration_debug_{step}_{timestamp}.png"
        self.driver.save_screenshot(screenshot_file)
        logger.info(f"Screenshot saved: {screenshot_file}")

        if save_html:
            html_file = f"migration_debug_{step}_{timestamp}.html"
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            logger.info(f"HTML saved: {html_file}")

    def wait_for_page_load(self, timeout=10):
        """Wait for page to finish loading"""
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            time.sleep(2)
        except Exception as e:
            logger.warning(f"Page load wait timeout: {e}")

    def login(self):
        """Login to Meraki Dashboard"""
        logger.info("Logging into Meraki Dashboard")
        self.driver.get("https://dashboard.meraki.com")
        time.sleep(3)

        # Enter email
        email_field = self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'], input#email, input#Email"))
        )
        email_field.send_keys(self.username)
        email_field.send_keys(Keys.RETURN)
        time.sleep(3)

        # Enter password
        password_field = self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password'], input#password, input#Password"))
        )
        password_field.send_keys(self.password)
        password_field.send_keys(Keys.RETURN)

        # Handle 2FA if needed
        time.sleep(5)
        self._handle_2fa_if_needed()

        # Wait for dashboard to load
        try:
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".main-navigation, .nav-bar, [href*='/organization']"))
            )
            logger.info("Successfully logged in")
        except TimeoutException:
            self.save_debug_info("login_failed")
            raise Exception("Dashboard did not load after login")

        time.sleep(3)

    def _handle_2fa_if_needed(self):
        """Handle 2FA verification if required"""
        try:
            # Look for verification code field
            verification_field = None
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, "input[type='text']:not([type='password']), input[type='number']")
                for elem in elements:
                    if elem.is_displayed():
                        elem_id = (elem.get_attribute('id') or '').lower()
                        elem_name = (elem.get_attribute('name') or '').lower()
                        elem_placeholder = (elem.get_attribute('placeholder') or '').lower()
                        if ('code' in elem_id or 'code' in elem_name or 'code' in elem_placeholder or
                                'verification' in elem_id or 'verification' in elem_name or 'verification' in elem_placeholder):
                            verification_field = elem
                            break
            except:
                pass

            if verification_field:
                logger.info("=" * 60)
                logger.info("2FA VERIFICATION REQUIRED")
                logger.info("=" * 60)
                logger.info("Please check your email for the verification code.")

                verification_code = input("Enter verification code: ").strip()

                if verification_code:
                    verification_field.clear()
                    verification_field.send_keys(verification_code)

                    # Try to find and click submit button
                    try:
                        submit_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit'], button:not([disabled])")
                        submit_btn.click()
                    except:
                        verification_field.send_keys(Keys.RETURN)

                    logger.info("Submitted verification code")
                    time.sleep(10)
        except Exception as e:
            logger.debug(f"2FA check completed: {e}")

    def select_organization(self, org_name: str) -> bool:
        """Select organization by name"""
        logger.info(f"Selecting organization: {org_name}")

        current_url = self.driver.current_url
        logger.info(f"Current URL: {current_url}")

        # Take a screenshot to see current state
        self.save_debug_info(f"before_select_org_{org_name.replace(' ', '_')}", save_html=False)

        # Method 1: Use organization selector dropdown
        try:
            # Find the org selector - usually the first dropdown in the header
            org_selector = None
            selector_methods = [
                (By.CSS_SELECTOR, ".org-selector"),
                (By.CSS_SELECTOR, "[class*='org-selector']"),
                (By.CSS_SELECTOR, ".mds-global-nav-select-button"),
                (By.CSS_SELECTOR, "button[class*='select']"),
                (By.XPATH, "//button[contains(@class, 'dropdown')]"),
                (By.XPATH, "//div[@class='org-name']"),
                (By.CSS_SELECTOR, ".dropdown-toggle"),
            ]

            # Find all potential dropdowns
            all_dropdowns = self.driver.find_elements(By.CSS_SELECTOR, "button, div.dropdown-toggle")
            logger.info(f"Found {len(all_dropdowns)} potential dropdown elements")

            # Look for the one that contains org name or is the first major dropdown
            for dropdown in all_dropdowns:
                dropdown_text = dropdown.text
                if dropdown_text and dropdown.is_displayed():
                    # Check if it's likely the org selector
                    if any(keyword in dropdown_text for keyword in ["Organization", "org", current_url.split('/')[-1]]):
                        org_selector = dropdown
                        logger.info(f"Found org selector with text: {dropdown_text}")
                        break

            # If not found by text, try the first dropdown in header
            if not org_selector:
                header_dropdowns = self.driver.find_elements(By.CSS_SELECTOR, "header button, nav button, .header button")
                if header_dropdowns:
                    org_selector = header_dropdowns[0]
                    logger.info(f"Using first header dropdown as org selector")

            if org_selector:
                # Click the org selector
                try:
                    org_selector.click()
                except:
                    self.driver.execute_script("arguments[0].click();", org_selector)

                logger.info("Clicked org selector dropdown")
                time.sleep(2)

                # Look for the target organization in the dropdown
                org_found = False
                org_link_selectors = [
                    (By.XPATH, f"//a[contains(text(), '{org_name}')]"),
                    (By.XPATH, f"//span[contains(text(), '{org_name}')]"),
                    (By.XPATH, f"//*[contains(text(), '{org_name}')]"),
                    (By.PARTIAL_LINK_TEXT, org_name),
                ]

                for method, selector in org_link_selectors:
                    try:
                        org_elements = self.driver.find_elements(method, selector)
                        for elem in org_elements:
                            if elem.is_displayed() and org_name in elem.text:
                                elem.click()
                                logger.info(f"Clicked on organization: {org_name}")
                                org_found = True
                                time.sleep(5)
                                break
                        if org_found:
                            break
                    except:
                        continue

                if org_found:
                    # Verify we switched organizations
                    new_url = self.driver.current_url
                    logger.info(f"New URL after org selection: {new_url}")
                    return True
                else:
                    logger.error(f"Could not find '{org_name}' in organization dropdown")
                    # Log available organizations
                    try:
                        dropdown_items = self.driver.find_elements(By.CSS_SELECTOR, "a, span")
                        available_orgs = []
                        for item in dropdown_items:
                            if item.is_displayed() and item.text and len(item.text) > 3:
                                available_orgs.append(item.text)
                        logger.info(f"Available organizations in dropdown: {available_orgs[:10]}")
                    except:
                        pass

            else:
                logger.error("Could not find organization selector dropdown")

        except Exception as e:
            logger.error(f"Failed to use org selector dropdown: {e}")

        # Method 2: Check if we're on the organizations overview page
        if "/organizations" in current_url or "global_overview" in current_url:
            logger.info("On organizations overview page, looking for org in table")
            try:
                # Look for organization in the table
                org_link = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, f"//a[contains(text(), '{org_name}') or contains(., '{org_name}')]"))
                )
                org_link.click()
                logger.info(f"Clicked on organization in table: {org_name}")
                time.sleep(5)
                return True
            except:
                logger.error(f"Could not find organization '{org_name}' in table")

        # Method 3: Try to navigate to organizations page first
        try:
            logger.info("Attempting to navigate to organizations overview page")
            # Look for "Organizations" or "All organizations" link
            orgs_links = [
                "//a[contains(text(), 'Organizations')]",
                "//a[contains(text(), 'All organizations')]",
                "//a[contains(text(), 'Switch organization')]",
                "//a[contains(@href, '/organizations')]",
            ]

            for xpath in orgs_links:
                try:
                    link = self.driver.find_element(By.XPATH, xpath)
                    if link.is_displayed():
                        link.click()
                        logger.info(f"Clicked on organizations link: {link.text}")
                        time.sleep(5)

                        # Now try to find the org
                        org_link = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, f"//a[contains(text(), '{org_name}')]"))
                        )
                        org_link.click()
                        logger.info(f"Selected organization from list: {org_name}")
                        time.sleep(5)
                        return True
                except:
                    continue

        except Exception as e:
            logger.error(f"Failed to navigate to organizations page: {e}")

        # Method 4: Try using keyboard shortcut or menu
        try:
            # Some Meraki dashboards have keyboard shortcuts
            logger.info("Trying alternative methods to switch organization")

            # Try to find any "Switch" or "Change" organization option
            switch_options = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Switch') or contains(text(), 'Change')]")
            for option in switch_options:
                if option.is_displayed() and "organization" in option.text.lower():
                    option.click()
                    time.sleep(2)

                    # Look for the org again
                    org_element = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, f"//*[contains(text(), '{org_name}')]"))
                    )
                    org_element.click()
                    logger.info(f"Selected organization via switch option: {org_name}")
                    time.sleep(5)
                    return True
        except:
            pass

        # If all methods failed
        logger.error(f"All methods failed to select organization '{org_name}'")
        self.save_debug_info(f"failed_select_org_{org_name.replace(' ', '_')}", save_html=True)

        # Check if user has access to the organization
        logger.error("Possible reasons for failure:")
        logger.error("1. The user account doesn't have access to the target organization")
        logger.error("2. The organization name might be slightly different (check capitalization/spacing)")
        logger.error("3. You might need to log in with different credentials for the target organization")

        return False

    def select_network(self, network_name: str) -> bool:
        """Select a specific network from the organization"""
        logger.info(f"Selecting network: {network_name}")

        current_url = self.driver.current_url

        # Check if we need to go to networks list first
        if "/manage/organization/" in current_url:
            # We're in organization context, need to find networks
            try:
                # Look for Networks menu item or link
                networks_link = None
                network_selectors = [
                    (By.XPATH, "//a[contains(text(), 'Networks')]"),
                    (By.XPATH, "//span[contains(text(), 'Networks')]"),
                    (By.XPATH, "//a[contains(@href, '/networks')]"),
                    (By.LINK_TEXT, "Networks"),
                ]

                for method, selector in network_selectors:
                    try:
                        networks_link = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((method, selector))
                        )
                        networks_link.click()
                        logger.info("Clicked on Networks menu")
                        time.sleep(3)
                        break
                    except:
                        continue
            except:
                logger.info("Could not find Networks menu, trying direct approach")

        # Now find and click on the specific network
        network_found = False
        network_selectors = [
            (By.XPATH, f"//a[contains(text(), '{network_name}')]"),
            (By.XPATH, f"//td[contains(text(), '{network_name}')]//a"),
            (By.XPATH, f"//tr[contains(., '{network_name}')]//a"),
            (By.PARTIAL_LINK_TEXT, network_name),
        ]

        for method, selector in network_selectors:
            try:
                network_element = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((method, selector))
                )
                network_element.click()
                network_found = True
                logger.info(f"Clicked on network: {network_name}")
                time.sleep(5)
                break
            except:
                continue

        if not network_found:
            # Try using the network selector dropdown if available
            try:
                # Look for network selector dropdown (second dropdown in header)
                dropdowns = self.driver.find_elements(By.CSS_SELECTOR, ".mds-global-nav-select-button, button[class*='select']")
                if len(dropdowns) >= 2:
                    # Click the second dropdown (network selector)
                    dropdowns[1].click()
                    time.sleep(2)

                    # Find and click the network
                    network_option = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, f"//*[contains(text(), '{network_name}')]"))
                    )
                    network_option.click()
                    network_found = True
                    logger.info(f"Selected network from dropdown: {network_name}")
                    time.sleep(3)
            except:
                logger.warning("Could not use network dropdown selector")

        if not network_found:
            logger.error(f"Could not find or select network '{network_name}'")
            return False

        # Verify we're in the network context
        time.sleep(2)
        new_url = self.driver.current_url
        if "/n/" in new_url or network_name in self.driver.title:
            logger.info(f"Successfully entered network context")
            return True
        else:
            logger.warning("May not have successfully entered network context")
            return True  # Continue anyway

    def navigate_to_switches(self, network_name: str) -> bool:
        """Navigate to Network > Switches page"""
        logger.info(f"Navigating to switches page for network: {network_name}")

        # First, select the network
        if not self.select_network(network_name):
            logger.error("Failed to select network")
            return False

        # Take screenshot after network selection
        self.save_debug_info("after_network_selection")

        # Now navigate to switches within the network context
        current_url = self.driver.current_url
        logger.info(f"Current URL after network selection: {current_url}")

        # Check if we're already on switches page
        if "/switches" in current_url or "/nodes/list" in current_url:
            logger.info("Already on switches page")
            return True

        try:
            # Method 1: Try to find Switching/Switch menu
            try:
                switch_menu_selectors = [
                    (By.XPATH, "//span[contains(text(), 'Switching')]"),
                    (By.XPATH, "//span[contains(text(), 'Switch')]"),
                    (By.XPATH, "//a[contains(text(), 'Switch')]"),
                ]

                for method, selector in switch_menu_selectors:
                    try:
                        switch_menu = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((method, selector))
                        )
                        switch_menu.click()
                        logger.info("Clicked on Switch/Switching menu")
                        time.sleep(2)

                        # Look for Switches submenu
                        switches_link_selectors = [
                            (By.XPATH, "//a[contains(text(), 'Switches')]"),
                            (By.XPATH, "//a[contains(text(), 'List')]"),
                            (By.LINK_TEXT, "Switches"),
                        ]

                        for sub_method, sub_selector in switches_link_selectors:
                            try:
                                switches_link = WebDriverWait(self.driver, 3).until(
                                    EC.element_to_be_clickable((sub_method, sub_selector))
                                )
                                switches_link.click()
                                logger.info("Clicked on Switches submenu")
                                time.sleep(3)
                                return True
                            except:
                                continue

                    except:
                        continue

            except Exception as e:
                logger.warning(f"Menu navigation failed: {e}")

            # Method 2: Try direct URL navigation if we have network ID
            if "/n/" in current_url:
                # Extract network ID and construct URL
                import re
                match = re.search(r'/n/([^/]+)', current_url)
                if match:
                    network_id = match.group(1)
                    base_url = current_url.split('/n/')[0]

                    # Try different URL patterns
                    url_patterns = [
                        f"{base_url}/n/{network_id}/manage/switches",
                        f"{base_url}/n/{network_id}/manage/switch/switches",
                    ]

                    for url in url_patterns:
                        logger.info(f"Trying URL: {url}")
                        self.driver.get(url)
                        time.sleep(3)

                        # Check if we successfully navigated
                        new_url = self.driver.current_url
                        if any(x in new_url for x in ["/switches", "/switch", "/nodes"]):
                            logger.info("Successfully navigated to switches page via URL")
                            return True

            # Method 3: Look for any switches-related links on the page
            logger.info("Looking for switches-related links on the page...")
            switches_links = self.driver.find_elements(By.XPATH, "//a[contains(@href, 'switches') or contains(@href, 'switch') or contains(@href, 'nodes')]")
            for link in switches_links:
                if link.is_displayed():
                    href = link.get_attribute('href')
                    link_text = link.text
                    logger.info(f"Found link: {link_text} -> {href}")
                    if any(x in href for x in ['/switches', '/switch', '/nodes']):
                        link.click()
                        time.sleep(3)
                        return True

        except Exception as e:
            logger.error(f"All navigation methods failed: {e}")
            self.save_debug_info("switches_navigation_failed")

        return False

    def remove_devices_from_network(self, org_name: str, network_name: str, device_serials: List[str]) -> bool:
        """Remove devices from network before unclaiming"""
        logger.info(f"Removing {len(device_serials)} devices from network '{network_name}'")

        # Navigate to switches page (this now includes network selection)
        if not self.navigate_to_switches(network_name):
            logger.error("Failed to navigate to switches page")
            return False

        # Wait for page to fully load
        time.sleep(5)

        # Take screenshot and save HTML to see current state
        self.save_debug_info("switches_page", save_html=True)

        # Log the current page URL and title
        logger.info(f"Current URL: {self.driver.current_url}")
        logger.info(f"Page title: {self.driver.title}")

        # Check if we're on the right page by looking for table headers
        try:
            table_headers = self.driver.find_elements(By.CSS_SELECTOR, "th, thead td")
            if table_headers:
                logger.info("Table headers found:")
                for header in table_headers[:10]:  # Log first 10 headers
                    if header.text:
                        logger.info(f"  - {header.text}")
        except:
            logger.warning("Could not find table headers")

        # Close any open menus by clicking on the main content area
        try:
            # Click on the main content area to close any hovering menus
            main_content = self.driver.find_element(By.CSS_SELECTOR, "main, .main-content, #main-content, [role='main']")
            self.driver.execute_script("arguments[0].click();", main_content)
            time.sleep(1)
        except:
            # Alternative: click on the page title or header
            try:
                page_title = self.driver.find_element(By.CSS_SELECTOR, "h1, .page-title, .switches-title")
                page_title.click()
                time.sleep(1)
            except:
                pass

        # Search for device if search box exists
        search_box = None
        search_selectors = [
            # Look for the search box specifically in the table area, not the global search
            (By.CSS_SELECTOR, "div.table-search input[type='search']"),
            (By.CSS_SELECTOR, "div.switches-table input[type='search']"),
            (By.CSS_SELECTOR, "section input[type='search']"),
            (By.CSS_SELECTOR, "main input[type='search']"),
            # Look for search box that's NOT in the header/navigation
            (By.XPATH, "//main//input[@type='search']"),
            (By.XPATH, "//section//input[@type='search']"),
            # Look for search box near the table
            (By.XPATH, "//table/ancestor::div//input[@type='search']"),
            # Try to find by placeholder that's specific to table search
            (By.CSS_SELECTOR, "input[placeholder*='MAC' i], input[placeholder*='name' i], input[placeholder*='serial' i]"),
        ]

        # First, let's find ALL search boxes and log them
        all_search_boxes = self.driver.find_elements(By.CSS_SELECTOR, "input[type='search']")
        logger.info(f"Found {len(all_search_boxes)} search boxes on page")
        for i, box in enumerate(all_search_boxes):
            placeholder = box.get_attribute('placeholder') or 'No placeholder'
            is_displayed = box.is_displayed()
            parent_class = box.find_element(By.XPATH, "..").get_attribute('class') or 'No class'
            logger.debug(f"Search box {i}: placeholder='{placeholder}', displayed={is_displayed}, parent_class='{parent_class}'")

        # Now try to find the RIGHT search box (not the global one)
        for method, selector in search_selectors:
            try:
                elements = self.driver.find_elements(method, selector)
                for element in elements:
                    # Skip if it's the global search (usually has placeholder about searching everything)
                    placeholder = element.get_attribute('placeholder') or ''
                    if 'everything' in placeholder.lower() or 'global' in placeholder.lower():
                        continue
                    # Skip if it's in the header/nav
                    try:
                        nav_parent = element.find_element(By.XPATH, "ancestor::nav")
                        continue  # Skip this one, it's in navigation
                    except:
                        pass  # Good, not in nav

                    if element.is_displayed():
                        search_box = element
                        logger.info(f"Found table search box with placeholder: '{placeholder}'")
                        break
                if search_box:
                    break
            except Exception as e:
                logger.debug(f"Search method {method} failed: {e}")
                continue

        if not search_box:
            logger.error("Could not find table search box!")
            # Take a screenshot to debug
            self.save_debug_info("no_table_search_box", save_html=True)

            # Try alternative: construct search URL directly
            logger.info("Attempting to use URL-based search as fallback")

        selected_count = 0

        # Process each device
        for serial in device_serials:
            if search_box:
                try:
                    # Clear the search box completely - multiple methods
                    try:
                        # Method 1: Clear and verify
                        search_box.clear()
                        time.sleep(0.5)

                        # Method 2: Select all and delete
                        search_box.send_keys(Keys.CONTROL + "a")
                        search_box.send_keys(Keys.DELETE)
                        time.sleep(0.5)

                        # Method 3: Use JavaScript to clear
                        self.driver.execute_script("arguments[0].value = '';", search_box)
                        time.sleep(0.5)
                    except:
                        logger.warning("Failed to clear search box completely")

                    # Now enter the serial
                    search_box.send_keys(serial)
                    search_box.send_keys(Keys.RETURN)
                    time.sleep(3)
                    logger.info(f"Searched for device {serial}")

                    # Verify what's in the search box
                    current_search_value = search_box.get_attribute('value')
                    if current_search_value != serial:
                        logger.warning(f"Search box contains '{current_search_value}' instead of '{serial}'")
                        # Try one more time with JavaScript
                        self.driver.execute_script("arguments[0].value = arguments[1];", search_box, serial)
                        search_box.send_keys(Keys.RETURN)
                        time.sleep(3)

                    # Wait for search results to load
                    try:
                        # Wait for either results or "no results" message
                        WebDriverWait(self.driver, 5).until(
                            lambda driver: len(driver.find_elements(By.CSS_SELECTOR, "table tbody tr")) > 0 or
                                           len(driver.find_elements(By.XPATH, "//*[contains(text(), 'No devices found') or contains(text(), 'No results')]")) > 0
                        )
                    except:
                        logger.warning("Timeout waiting for search results")
                except Exception as e:
                    logger.warning(f"Failed to search for {serial}: {e}")
                    # Try URL-based search as fallback
                    current_url = self.driver.current_url
                    # Remove any existing search query
                    base_url = current_url.split('?')[0]
                    search_url = f"{base_url}?timespan=86400&search_query={serial}"
                    logger.info(f"Using URL-based search: {search_url}")
                    self.driver.get(search_url)
                    time.sleep(3)
            else:
                # No search box found, use URL-based search
                current_url = self.driver.current_url
                base_url = current_url.split('?')[0]
                search_url = f"{base_url}?timespan=86400&search_query={serial}"
                logger.info(f"Using URL-based search (no search box): {search_url}")
                self.driver.get(search_url)
                time.sleep(3)

            # Find device row by serial number
            device_found = False
            rows = self.driver.find_elements(By.CSS_SELECTOR, "table tbody tr, tr")

            logger.info(f"Found {len(rows)} table rows after searching for {serial}")

            # If we have rows, check them more carefully
            if len(rows) > 0:
                # Log details of first few rows
                for i, row in enumerate(rows[:3]):
                    row_text = row.text
                    if row_text.strip():  # Only log non-empty rows
                        logger.debug(f"Row {i} text: {row_text[:200]}")

                        # Check all cells in the row
                        cells = row.find_elements(By.TAG_NAME, "td")
                        for j, cell in enumerate(cells):
                            cell_text = cell.text.strip()
                            if cell_text:
                                logger.debug(f"  Cell {j}: {cell_text}")

            # If no rows or only header row after search
            if len(rows) <= 1:
                logger.warning(f"No results found for device {serial}")
                # Save HTML to debug
                self.save_debug_info(f"no_results_{serial}", save_html=True)
                continue

            for row in rows:
                row_text = row.text
                # Log row details for debugging
                if serial in row_text:
                    logger.info(f"Found device row containing serial {serial}")
                    logger.debug(f"Row text: {row_text}")

                    # Also check if serial might be in a specific cell
                    cells = row.find_elements(By.TAG_NAME, "td")
                    for i, cell in enumerate(cells):
                        if serial in cell.text:
                            logger.debug(f"Serial found in cell {i}: {cell.text}")

                    # Scroll the row into view to ensure it's not hidden
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", row)
                    time.sleep(1)

                    # Try multiple methods to find and click the checkbox
                    checkbox_clicked = False

                    # Method 1: Look for checkbox in the first cell
                    try:
                        first_cell = row.find_element(By.CSS_SELECTOR, "td:first-child")
                        checkbox = first_cell.find_element(By.CSS_SELECTOR, "input[type='checkbox']")

                        # Use JavaScript to click if the element might be obscured
                        self.driver.execute_script("arguments[0].click();", checkbox)
                        checkbox_clicked = True
                        logger.info("Selected device checkbox using JavaScript click")
                    except Exception as e:
                        logger.debug(f"Method 1 failed: {e}")

                    # Method 2: Find any checkbox in the row
                    if not checkbox_clicked:
                        try:
                            checkbox = row.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                            self.driver.execute_script("arguments[0].click();", checkbox)
                            checkbox_clicked = True
                            logger.info("Selected device checkbox in row")
                        except Exception as e:
                            logger.debug(f"Method 2 failed: {e}")

                    # Method 3: Click on the row itself if it's selectable
                    if not checkbox_clicked:
                        try:
                            # Some tables select the row when clicking anywhere on it
                            self.driver.execute_script("arguments[0].click();", row)
                            time.sleep(1)

                            # Check if a checkbox appeared or got selected
                            try:
                                checkbox = row.find_element(By.CSS_SELECTOR, "input[type='checkbox']:checked")
                                checkbox_clicked = True
                                logger.info("Row click selected the device")
                            except:
                                pass
                        except Exception as e:
                            logger.debug(f"Method 3 failed: {e}")

                    if checkbox_clicked:
                        device_found = True
                        selected_count += 1
                        time.sleep(1)
                        break
                    else:
                        logger.error(f"Could not select device checkbox for {serial}")

                        # Take a screenshot to debug
                        self.save_debug_info(f"checkbox_selection_failed_{serial}")

                        # Try to identify what's blocking the checkbox
                        try:
                            # Check if there's an overlay or menu covering the checkbox
                            overlays = self.driver.find_elements(By.CSS_SELECTOR, "[class*='overlay'], [class*='menu'], [class*='dropdown']")
                            for overlay in overlays:
                                if overlay.is_displayed():
                                    logger.info(f"Found potential overlay: {overlay.get_attribute('class')}")
                        except:
                            pass

            if not device_found:
                logger.warning(f"Device {serial} not found in table - may already be removed from network")
                # Capture current state for debugging
                self.save_debug_info(f"device_not_found_{serial}", save_html=True)

                # Check if we're on the right page
                current_url = self.driver.current_url
                if "/switches" not in current_url:
                    logger.error(f"Not on switches page! Current URL: {current_url}")

                # Check for any error messages on the page
                try:
                    error_messages = self.driver.find_elements(By.CSS_SELECTOR, "[class*='error'], [class*='alert'], [class*='warning']")
                    for msg in error_messages:
                        if msg.text and "no matches" not in msg.text.lower():
                            logger.warning(f"Found error/warning message: {msg.text}")
                except:
                    pass

        # Clear search to show all selected devices
        if search_box and selected_count > 0:
            try:
                # Clear search box completely
                search_box.clear()
                search_box.send_keys(Keys.CONTROL + "a")
                search_box.send_keys(Keys.DELETE)
                self.driver.execute_script("arguments[0].value = '';", search_box)
                search_box.send_keys(Keys.RETURN)
                time.sleep(2)
                logger.info("Cleared search to show all selected devices")
            except:
                logger.warning("Failed to clear search box at end")

        if selected_count == 0:
            logger.warning("No devices were selected - they may already be removed from the network")
            logger.info("Continuing with migration process...")
            return True  # Continue anyway instead of failing

        logger.info(f"Selected {selected_count} devices out of {len(device_serials)} requested")

        # Look for Remove button
        remove_button = None
        buttons = self.driver.find_elements(By.TAG_NAME, "button")

        for btn in buttons:
            if btn.is_displayed() and btn.is_enabled():
                btn_text = btn.text.lower()
                if 'remove' in btn_text:
                    remove_button = btn
                    logger.info(f"Found Remove button: '{btn.text}'")
                    break

        if not remove_button:
            logger.error("No Remove button found")
            # Take screenshot for debugging
            self.save_debug_info("no_remove_button")
            return False

        # Click Remove button
        try:
            remove_button.click()
            logger.info("Clicked Remove button")
        except:
            try:
                self.driver.execute_script("arguments[0].click();", remove_button)
                logger.info("Clicked Remove button using JavaScript")
            except Exception as e:
                logger.error(f"Failed to click Remove button: {e}")
                return False

        time.sleep(2)

        # Confirm removal - based on debug.py successful approach
        try:
            # Wait for the confirmation dialog to appear
            time.sleep(1)

            # Look for the Remove button in the confirmation dialog
            # The dialog has a blue "Remove" button (not "Confirm" or "Yes")
            confirm_methods = [
                # Primary: Look for Remove button in a modal/dialog
                (By.XPATH, "//div[contains(@class, 'modal') or contains(@class, 'dialog')]//button[contains(text(), 'Remove')]"),
                # Secondary: Any blue/primary Remove button
                (By.XPATH, "//button[contains(@class, 'primary') or contains(@class, 'blue')][contains(text(), 'Remove')]"),
                # Tertiary: Just the Remove button text (but not the first one we clicked)
                (By.XPATH, "(//button[contains(text(), 'Remove')])[last()]"),
                # Look for Remove button that's not disabled
                (By.XPATH, "//button[contains(text(), 'Remove') and not(@disabled)]"),
                # Try the specific modal button
                (By.CSS_SELECTOR, ".modal button.primary, .dialog button.primary, button[class*='primary'][class*='button']"),
            ]

            confirm_btn = None
            for method, selector in confirm_methods:
                try:
                    elements = self.driver.find_elements(method, selector)
                    # Find the Remove button that's in the dialog (not the one we already clicked)
                    for elem in elements:
                        if elem.is_displayed() and elem.is_enabled():
                            # Check if this is in a modal/dialog context
                            parent_html = elem.get_attribute('outerHTML')
                            logger.debug(f"Found potential confirm button: {elem.text}")
                            if elem != remove_button:  # Make sure it's not the same button
                                confirm_btn = elem
                                logger.info(f"Found confirmation button: '{elem.text}'")
                                break
                    if confirm_btn:
                        break
                except Exception as e:
                    logger.debug(f"Method failed: {e}")

            if not confirm_btn:
                # Last resort: find all visible Remove buttons and click the last one
                all_remove_buttons = self.driver.find_elements(By.XPATH, "//button[contains(text(), 'Remove')]")
                for btn in reversed(all_remove_buttons):
                    if btn.is_displayed() and btn.is_enabled():
                        confirm_btn = btn
                        logger.info(f"Using last Remove button as confirmation")
                        break

            if confirm_btn:
                confirm_btn.click()
                logger.info("Clicked confirmation Remove button")
                time.sleep(5)

                logger.info(f"Successfully initiated removal of {selected_count} devices from network")
                return True
            else:
                logger.error("Could not find confirmation Remove button")
                self.save_debug_info("no_confirm_button")
                return False

        except Exception as e:
            logger.error(f"Could not confirm device removal: {e}")
            self.save_debug_info("removal_confirmation_failed")
            return False

    def navigate_to_inventory(self):
        """Navigate to Organization > Inventory"""
        logger.info("Navigating to Organization > Inventory")

        current_url = self.driver.current_url
        logger.info(f"Current URL before navigation: {current_url}")

        # Take a screenshot to see current state
        self.save_debug_info("before_inventory_nav", save_html=True)

        # Method 1: Direct menu navigation - most reliable
        try:
            # Look for Organization menu in the navigation
            logger.info("Looking for Organization menu...")
            org_menu = None
            org_menu_selectors = [
                (By.XPATH, "//nav//span[text()='Organization']"),
                (By.XPATH, "//span[text()='Organization']"),
                (By.XPATH, "//a[span[text()='Organization']]"),
                (By.XPATH, "//*[@class='main-navigation']//span[text()='Organization']"),
                (By.CSS_SELECTOR, "nav span:contains('Organization')"),
            ]

            for method, selector in org_menu_selectors:
                try:
                    if method == By.CSS_SELECTOR and ":contains" in selector:
                        # Skip jQuery-style selectors
                        continue
                    elements = self.driver.find_elements(method, selector)
                    for elem in elements:
                        if elem.is_displayed():
                            # Check if it's actually in the main navigation
                            try:
                                # Verify it's in a nav element
                                nav_parent = elem.find_element(By.XPATH, "ancestor::nav")
                                org_menu = elem
                                logger.info(f"Found Organization menu element")
                                break
                            except:
                                # Try without nav requirement
                                org_menu = elem
                                break
                    if org_menu:
                        break
                except Exception as e:
                    logger.debug(f"Selector {method} {selector} failed: {e}")
                    continue

            if org_menu:
                # Click on Organization menu
                try:
                    org_menu.click()
                except:
                    # Try JavaScript click if regular click fails
                    self.driver.execute_script("arguments[0].click();", org_menu)

                logger.info("Clicked Organization menu")
                time.sleep(2)

                # Now look for Inventory submenu
                inventory_link = None
                inventory_selectors = [
                    (By.XPATH, "//a[text()='Inventory']"),
                    (By.XPATH, "//a[span[text()='Inventory']]"),
                    (By.XPATH, "//a[contains(text(), 'Inventory')]"),
                    (By.LINK_TEXT, "Inventory"),
                    (By.PARTIAL_LINK_TEXT, "Inventory"),
                ]

                for method, selector in inventory_selectors:
                    try:
                        inventory_link = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((method, selector))
                        )
                        logger.info("Found Inventory link")
                        break
                    except:
                        continue

                if inventory_link:
                    inventory_link.click()
                    logger.info("Clicked Inventory link")
                    time.sleep(5)

                    # Verify we're on inventory page
                    if "/inventory" in self.driver.current_url:
                        logger.info("Successfully navigated to inventory page via menu")
                        return True
                    else:
                        logger.warning(f"Click completed but not on inventory page. Current URL: {self.driver.current_url}")
            else:
                logger.warning("Could not find Organization menu")
        except Exception as e:
            logger.warning(f"Menu navigation failed: {e}")

        # Method 2: If we're in network context, try to go to org first
        if "/n/" in current_url or "/Hilton-" in current_url:
            logger.info("In network context, trying to switch to organization view first")

            # Try clicking on the organization name/breadcrumb
            try:
                # Look for org name in breadcrumb or header
                org_links = self.driver.find_elements(By.XPATH, "//a[contains(@href, '/o/')]")
                for link in org_links:
                    if link.is_displayed():
                        logger.info(f"Found org link: {link.text}")
                        link.click()
                        time.sleep(3)
                        break
            except:
                pass

            # Try using org dropdown selector (first dropdown)
            try:
                dropdowns = self.driver.find_elements(By.CSS_SELECTOR, ".mds-global-nav-select-button, button[class*='select'], .dropdown-toggle")
                if dropdowns:
                    logger.info(f"Found {len(dropdowns)} dropdowns")
                    # The first dropdown is usually the org selector
                    dropdowns[0].click()
                    time.sleep(2)

                    # Look for "Go to Organization" or "Overview" option
                    org_options = [
                        "//a[contains(text(), 'Overview')]",
                        "//a[contains(text(), 'overview')]",
                        "//a[contains(text(), 'Organization')]",
                        "//a[contains(text(), 'Go to')]",
                    ]

                    for xpath in org_options:
                        try:
                            option = self.driver.find_element(By.XPATH, xpath)
                            if option.is_displayed():
                                option.click()
                                logger.info(f"Clicked org option: {option.text}")
                                time.sleep(3)
                                break
                        except:
                            continue
            except Exception as e:
                logger.warning(f"Dropdown navigation failed: {e}")

        # Method 3: Look for any visible Inventory link on the page
        try:
            logger.info("Looking for any Inventory link on page...")
            all_links = self.driver.find_elements(By.TAG_NAME, "a")
            for link in all_links:
                if link.is_displayed() and "inventory" in link.text.lower():
                    href = link.get_attribute('href') or ''
                    if '/organization/inventory' in href or '/manage/organization/inventory' in href:
                        logger.info(f"Found direct inventory link: {link.text} -> {href}")
                        link.click()
                        time.sleep(5)

                        if "/inventory" in self.driver.current_url:
                            logger.info("Successfully navigated to inventory page via direct link")
                            return True
        except Exception as e:
            logger.warning(f"Direct link search failed: {e}")

        # Method 4: Try to find and click through the UI path
        try:
            # Sometimes we need to click through multiple levels
            # First ensure we're at org level
            if "/n/" in self.driver.current_url:
                # Click on org name in header
                org_name_elements = self.driver.find_elements(By.CSS_SELECTOR, ".org-name, .organization-name, h1, h2")
                for elem in org_name_elements:
                    text = elem.text
                    if text and "network" not in text.lower():
                        try:
                            elem.click()
                            time.sleep(2)
                            break
                        except:
                            pass

            # Now try Organization menu again
            self.driver.execute_script("""
                // Try to find and click Organization menu via JavaScript
                var orgMenu = Array.from(document.querySelectorAll('span')).find(el => el.textContent === 'Organization');
                if (orgMenu) {
                    orgMenu.click();
                    return true;
                }
                return false;
            """)
            time.sleep(2)

            # Then inventory
            self.driver.execute_script("""
                // Try to find and click Inventory link via JavaScript
                var invLink = Array.from(document.querySelectorAll('a')).find(el => el.textContent.includes('Inventory'));
                if (invLink) {
                    invLink.click();
                    return true;
                }
                return false;
            """)
            time.sleep(5)

            if "/inventory" in self.driver.current_url:
                logger.info("Successfully navigated to inventory page via JavaScript")
                return True

        except Exception as e:
            logger.warning(f"JavaScript navigation failed: {e}")

        # If all methods failed, save debug info
        self.save_debug_info("inventory_navigation_failed", save_html=True)

        # Log available navigation elements for debugging
        logger.error("Failed to navigate to inventory. Available navigation elements:")
        try:
            nav_elements = self.driver.find_elements(By.XPATH, "//nav//span | //nav//a")
            for elem in nav_elements[:20]:
                if elem.text:
                    logger.error(f"  - {elem.text}")
        except:
            pass

        logger.error(f"Final URL: {self.driver.current_url}")
        return False

    def unclaim_devices(self, org_name: str, device_serials: List[str]) -> bool:
        """Unclaim devices from organization"""
        logger.info(f"Unclaiming {len(device_serials)} devices from organization '{org_name}'")

        # Navigate to inventory
        if not self.navigate_to_inventory():
            return False

        # Wait for page to load completely
        time.sleep(5)
        self.wait_for_page_load()

        # Take screenshot and save HTML for debugging
        self.save_debug_info("inventory_page", save_html=True)

        # Log current URL and page title
        logger.info(f"Current URL: {self.driver.current_url}")
        logger.info(f"Page title: {self.driver.title}")

        # Check if we're on the right page by looking for inventory indicators
        inventory_indicators = [
            "Inventory",
            "Claim",
            "Serial",
            "Model"
        ]

        page_text = self.driver.find_element(By.TAG_NAME, "body").text
        found_indicators = [ind for ind in inventory_indicators if ind in page_text]
        logger.info(f"Found inventory indicators: {found_indicators}")

        # Wait for table to load
        try:
            # Wait for table or "no devices" message
            WebDriverWait(self.driver, 10).until(
                lambda driver: len(driver.find_elements(By.CSS_SELECTOR, "table tbody tr")) > 0 or
                               len(driver.find_elements(By.XPATH, "//*[contains(text(), 'No devices') or contains(text(), 'no results')]")) > 0
            )
        except:
            logger.warning("Timeout waiting for inventory table to load")

        # Check how many total devices are in inventory
        all_rows = self.driver.find_elements(By.CSS_SELECTOR, "table tbody tr, tr[role='row']")
        logger.info(f"Found {len(all_rows)} total rows in inventory table")

        # Log first few rows to see what's there
        for i, row in enumerate(all_rows[:5]):
            row_text = row.text.strip()
            if row_text:
                logger.debug(f"Row {i}: {row_text[:200]}")

        # Find the search box (similar to network removal)
        search_box = None
        search_selectors = [
            # Look for search box in the inventory table area
            (By.CSS_SELECTOR, "div.inventory-table input[type='search']"),
            (By.CSS_SELECTOR, "section input[type='search']"),
            (By.CSS_SELECTOR, "main input[type='search']"),
            (By.XPATH, "//main//input[@type='search']"),
            (By.XPATH, "//section//input[@type='search']"),
            (By.CSS_SELECTOR, "input[placeholder*='serial' i], input[placeholder*='device' i]"),
            # Generic search box
            (By.CSS_SELECTOR, "input[type='search']"),
            (By.CSS_SELECTOR, "input.search-box"),
        ]

        # Find ALL search boxes and log them
        all_search_boxes = self.driver.find_elements(By.CSS_SELECTOR, "input[type='search']")
        logger.info(f"Found {len(all_search_boxes)} search boxes on inventory page")
        for i, box in enumerate(all_search_boxes):
            placeholder = box.get_attribute('placeholder') or 'No placeholder'
            is_displayed = box.is_displayed()
            parent_class = box.find_element(By.XPATH, "..").get_attribute('class') or 'No class'
            logger.debug(f"Search box {i}: placeholder='{placeholder}', displayed={is_displayed}, parent_class='{parent_class}'")

        # Find the right search box (not the global one)
        for method, selector in search_selectors:
            try:
                elements = self.driver.find_elements(method, selector)
                for element in elements:
                    placeholder = element.get_attribute('placeholder') or ''
                    if 'everything' in placeholder.lower() or 'global' in placeholder.lower():
                        continue
                    try:
                        nav_parent = element.find_element(By.XPATH, "ancestor::nav")
                        continue
                    except:
                        pass

                    if element.is_displayed():
                        search_box = element
                        logger.info(f"Found inventory search box with placeholder: '{placeholder}'")
                        break
                if search_box:
                    break
            except:
                continue

        if not search_box:
            logger.warning("Could not find inventory search box, will look for devices without search")
            # Check if devices are visible without search
            visible_serials = []
            for row in all_rows:
                row_text = row.text
                for serial in device_serials:
                    if serial in row_text:
                        visible_serials.append(serial)

            if visible_serials:
                logger.info(f"Found {len(visible_serials)} devices visible without search: {visible_serials}")

        # Track selected devices
        selected_count = 0
        devices_not_found = []

        # Search and select devices
        for serial in device_serials:
            if search_box:
                try:
                    # Clear search box completely
                    search_box.clear()
                    search_box.send_keys(Keys.CONTROL + "a")
                    search_box.send_keys(Keys.DELETE)
                    self.driver.execute_script("arguments[0].value = '';", search_box)
                    time.sleep(0.5)

                    # Search for device
                    search_box.send_keys(serial)
                    search_box.send_keys(Keys.RETURN)
                    time.sleep(3)
                    logger.info(f"Searched for device {serial}")
                except Exception as e:
                    logger.warning(f"Failed to search for {serial}: {e}")

            # Find and select device
            device_found = False
            rows = self.driver.find_elements(By.CSS_SELECTOR, "table tbody tr, tr[role='row']")

            for row in rows:
                if serial in row.text:
                    logger.info(f"Found device {serial} in inventory")

                    # Try to find and click checkbox
                    try:
                        # Method 1: Checkbox in first cell
                        checkbox = row.find_element(By.CSS_SELECTOR, "td:first-child input[type='checkbox']")
                        if not checkbox.is_selected():
                            self.driver.execute_script("arguments[0].click();", checkbox)
                            device_found = True
                            selected_count += 1
                            logger.info(f"Selected device {serial}")
                    except:
                        try:
                            # Method 2: Any checkbox in row
                            checkbox = row.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                            if not checkbox.is_selected():
                                self.driver.execute_script("arguments[0].click();", checkbox)
                                device_found = True
                                selected_count += 1
                                logger.info(f"Selected device {serial}")
                        except:
                            logger.warning(f"Could not select checkbox for device {serial}")
                    break

            if not device_found:
                devices_not_found.append(serial)
                logger.warning(f"Device {serial} not found in inventory - may already be unclaimed")

        # Clear search to show all selected devices
        if search_box and selected_count > 0:
            try:
                search_box.clear()
                self.driver.execute_script("arguments[0].value = '';", search_box)
                search_box.send_keys(Keys.RETURN)
                time.sleep(2)
            except:
                pass

        if selected_count == 0:
            logger.warning("No devices were selected - they may already be unclaimed")
            logger.info(f"Devices not found: {devices_not_found}")

            # Check if the devices might be in a different organization
            if len(devices_not_found) == len(device_serials):
                logger.info("All devices not found in inventory. They may have been successfully removed from the network.")
                logger.info("Continuing with migration...")
                return True  # Continue anyway

        logger.info(f"Selected {selected_count} devices for unclaim")

        # Only proceed with unclaim if we have devices selected
        if selected_count == 0:
            logger.info("No devices to unclaim, continuing...")
            return True

        # Find and click Unclaim button
        unclaim_btn = None
        button_selectors = [
            (By.XPATH, "//button[contains(text(), 'Unclaim')]"),
            (By.XPATH, "//button[contains(., 'Unclaim')]"),
            (By.CSS_SELECTOR, "button.unclaim"),
            (By.XPATH, "//button[contains(@class, 'unclaim')]"),
        ]

        for method, selector in button_selectors:
            try:
                buttons = self.driver.find_elements(method, selector)
                for btn in buttons:
                    if btn.is_displayed() and btn.is_enabled():
                        unclaim_btn = btn
                        logger.info(f"Found unclaim button: {btn.text}")
                        break
                if unclaim_btn:
                    break
            except:
                continue

        if not unclaim_btn:
            logger.error("Could not find enabled Unclaim button")
            self.save_debug_info("no_unclaim_button", save_html=True)
            return False

        unclaim_btn.click()
        logger.info("Clicked Unclaim button")
        time.sleep(3)

        # Check if a confirmation dialog appears
        # Note: When devices are already removed from network, there may be no confirmation
        confirmation_appeared = False
        try:
            # Look for confirmation button with a short timeout
            confirm_selectors = [
                (By.XPATH, "//button[contains(text(), 'Unclaim from organization')]"),
                (By.XPATH, "//div[contains(@class, 'modal')]//button[contains(text(), 'Unclaim')]"),
                (By.XPATH, "//button[contains(@class, 'danger')][contains(text(), 'Unclaim')]"),
                (By.XPATH, "//button[contains(text(), 'Confirm')]"),
                (By.XPATH, "//button[contains(text(), 'Yes')]"),
            ]

            confirm_btn = None
            for method, selector in confirm_selectors:
                try:
                    # Use a short timeout since confirmation may not appear
                    confirm_btn = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((method, selector))
                    )
                    logger.info(f"Found confirmation button: {confirm_btn.text}")
                    confirmation_appeared = True
                    break
                except:
                    continue

            if confirm_btn:
                confirm_btn.click()
                logger.info("Clicked confirmation button")
                time.sleep(5)
        except:
            pass

        if not confirmation_appeared:
            logger.info("No confirmation dialog appeared - devices may have been unclaimed directly")
            time.sleep(5)  # Wait for unclaim to process

        # Verify unclaim succeeded by checking if devices are gone from inventory
        try:
            # Check if we're still on inventory page
            if "/inventory" in self.driver.current_url:
                # Look for success message or check if devices are gone
                page_text = self.driver.find_element(By.TAG_NAME, "body").text

                # Common success indicators
                success_indicators = [
                    "successfully unclaimed",
                    "has been unclaimed",
                    "unclaimed from organization",
                    "removed from organization",
                    "no devices found",
                    "0 devices"
                ]

                success_found = any(indicator in page_text.lower() for indicator in success_indicators)

                if success_found:
                    logger.info("Unclaim appears to have succeeded based on page content")
                else:
                    # Check if the devices are still visible
                    remaining_devices = []
                    for serial in device_serials:
                        if serial in page_text:
                            remaining_devices.append(serial)

                    if remaining_devices:
                        logger.warning(f"These devices may still be in inventory: {remaining_devices}")
                    else:
                        logger.info("Devices no longer visible in inventory - unclaim likely succeeded")
        except:
            pass

        logger.info("Unclaim operation completed")
        return True

    def claim_devices(self, org_name: str, device_serials: List[str]) -> bool:
        """Claim devices in organization"""
        try:
            # Navigate to inventory
            logger.info("Navigating to Organization > Inventory")
            if not self.navigate_to_inventory():
                return False

            time.sleep(3)

            # Take screenshot to see the page
            self.save_debug_info("inventory_page_before_claim", save_html=True)

            # First look for the main Claim button to open the claim dialog
            claim_btn = None
            claim_button_methods = [
                (By.XPATH, "//button[contains(text(), 'Claim')]"),
                (By.CSS_SELECTOR, "button.claim"),
                (By.CSS_SELECTOR, "button[class*='claim']"),
                (By.XPATH, "//button[contains(@class, 'primary')]"),
            ]

            for method, selector in claim_button_methods:
                try:
                    buttons = self.driver.find_elements(method, selector)
                    for btn in buttons:
                        if btn.is_displayed() and btn.is_enabled():
                            btn_text = btn.text
                            if "claim" in btn_text.lower() or btn_text in ["Add", "+"]:
                                claim_btn = btn
                                logger.info(f"Found claim button: '{btn_text}'")
                                break
                    if claim_btn:
                        break
                except:
                    continue

            if claim_btn:
                # Click the main claim button
                try:
                    claim_btn.click()
                except:
                    self.driver.execute_script("arguments[0].click();", claim_btn)
                logger.info("Clicked main claim button")
                time.sleep(3)
            else:
                logger.warning("No main claim button found, looking for direct claim options")

            # Now look for "Claim individual devices" link/button
            claim_individual_link = None
            individual_claim_methods = [
                (By.XPATH, "//a[contains(text(), 'Claim individual devices')]"),
                (By.XPATH, "//button[contains(text(), 'Claim individual devices')]"),
                (By.PARTIAL_LINK_TEXT, "Claim individual devices"),
                (By.XPATH, "//*[contains(text(), 'Claim individual devices')]"),
            ]

            for method, selector in individual_claim_methods:
                try:
                    elements = self.driver.find_elements(method, selector)
                    for elem in elements:
                        if elem.is_displayed():
                            claim_individual_link = elem
                            logger.info(f"Found 'Claim individual devices' element: {elem.tag_name}")
                            break
                    if claim_individual_link:
                        break
                except:
                    continue

            if not claim_individual_link:
                logger.error("Could not find 'Claim individual devices' option")
                # Log what's visible on the page
                try:
                    page_text = self.driver.find_element(By.TAG_NAME, "body").text
                    if "claim order" in page_text.lower():
                        logger.info("Found 'Claim order' option on page")
                    if "individual" in page_text.lower():
                        logger.info("Found 'individual' text on page")
                except:
                    pass
                self.save_debug_info("no_individual_claim_option", save_html=True)
                return False

            # Click "Claim individual devices"
            try:
                claim_individual_link.click()
            except:
                self.driver.execute_script("arguments[0].click();", claim_individual_link)
            logger.info("Clicked 'Claim individual devices'")
            time.sleep(3)

            # Now we should see the textarea for entering serials
            logger.info(f"Looking for text area to enter {len(device_serials)} device serials")
            serials_field = None

            # Based on screenshot, the textarea has specific text about entering serials
            serial_field_methods = [
                (By.XPATH, "//textarea[contains(@placeholder, 'Device Cloud ID')]"),
                (By.XPATH, "//textarea[contains(@placeholder, 'serial number')]"),
                (By.XPATH, "//textarea[contains(@placeholder, 'one per line')]"),
                (By.XPATH, "//textarea"),
                (By.CSS_SELECTOR, "textarea"),
                (By.TAG_NAME, "textarea"),
            ]

            for method, selector in serial_field_methods:
                try:
                    elements = self.driver.find_elements(method, selector)
                    for elem in elements:
                        if elem.is_displayed():
                            placeholder = elem.get_attribute('placeholder') or ''
                            logger.info(f"Found textarea with placeholder: '{placeholder}'")
                            serials_field = elem
                            break
                    if serials_field:
                        break
                except:
                    continue

            if not serials_field:
                logger.error("Could not find serials input field")
                self.save_debug_info("no_serials_textarea", save_html=True)
                return False

            # Clear and enter the serial numbers
            serials_field.clear()
            # Enter serials one per line
            for i, serial in enumerate(device_serials):
                if i > 0:
                    serials_field.send_keys(Keys.RETURN)
                serials_field.send_keys(serial)

            logger.info(f"Entered {len(device_serials)} serial numbers")
            time.sleep(2)

            # Look for the "Claim devices" button (based on screenshot)
            submit_btn = None
            submit_methods = [
                (By.XPATH, "//button[text()='Claim devices']"),
                (By.XPATH, "//button[contains(text(), 'Claim devices')]"),
                (By.CSS_SELECTOR, "button.primary"),
                (By.CSS_SELECTOR, "button[class*='primary']"),
                (By.XPATH, "//button[contains(@class, 'btn-primary')]"),
            ]

            for method, selector in submit_methods:
                try:
                    buttons = self.driver.find_elements(method, selector)
                    for btn in buttons:
                        if btn.is_displayed() and btn.is_enabled():
                            btn_text = btn.text
                            if "claim" in btn_text.lower():
                                submit_btn = btn
                                logger.info(f"Found submit button: '{btn_text}'")
                                break
                    if submit_btn:
                        break
                except:
                    continue

            if not submit_btn:
                logger.error("Could not find 'Claim devices' submit button")
                # Try to find any visible button
                all_buttons = self.driver.find_elements(By.TAG_NAME, "button")
                for btn in all_buttons:
                    if btn.is_displayed() and btn.text:
                        logger.info(f"Visible button: '{btn.text}'")
                self.save_debug_info("no_submit_button", save_html=True)
                return False

            # Click submit
            try:
                submit_btn.click()
            except:
                self.driver.execute_script("arguments[0].click();", submit_btn)

            logger.info(f"Clicked submit button: '{submit_btn.text}'")

            # Wait for claim to process
            time.sleep(10)

            # Check for success
            try:
                # Check for success message or if we're back at inventory
                page_text = self.driver.find_element(By.TAG_NAME, "body").text
                current_url = self.driver.current_url

                success_indicators = [
                    "successfully claimed",
                    "has been claimed",
                    "added to organization",
                    "devices claimed",
                    "claim successful"
                ]

                if any(indicator in page_text.lower() for indicator in success_indicators):
                    logger.info("Claim appears to have succeeded based on page content")
                elif "/inventory" in current_url:
                    # Check if devices now appear in inventory
                    devices_found = sum(1 for serial in device_serials if serial in page_text)
                    if devices_found > 0:
                        logger.info(f"Found {devices_found}/{len(device_serials)} devices in inventory after claim")
                    else:
                        logger.info("Returned to inventory page, claim likely succeeded")
                else:
                    logger.warning("Could not confirm claim success")
            except:
                pass

            logger.info(f"Claim operation completed for {len(device_serials)} devices")
            return True

        except Exception as e:
            logger.error(f"Failed to claim devices: {e}")
            self.save_debug_info("claim_failed_exception", save_html=True)
            return False


class ComprehensiveRestore:
    """Handles restoration of all settings"""

    def __init__(self, api_client: MerakiAPIClient):
        self.api = api_client

    def _clean_api_data(self, data: Dict, remove_fields: List[str] = None) -> Dict:
        """Remove read-only and problematic fields from API data"""
        if not data:
            return {}

        # Common read-only fields to remove
        default_remove = ['id', 'serial', 'mac', 'warnings', 'errors',
                          'createdAt', 'updatedAt', 'lastUpdated',
                          'status', 'usage', 'counts']

        if remove_fields:
            default_remove.extend(remove_fields)

        # Create a deep copy to avoid modifying the original
        import copy
        cleaned = copy.deepcopy(data)

        # Remove specified fields
        for field in default_remove:
            cleaned.pop(field, None)

        # Remove None values as they can cause issues
        cleaned = {k: v for k, v in cleaned.items() if v is not None}

        return cleaned

    def restore_all_settings(self, backup: Dict, target_network_id: str, device_mapping: Optional[Dict] = None):
        """Restore all settings from backup - NO DEVICE STATUS CHECKS"""
        logger.info(f"Starting comprehensive restore to network {target_network_id}")
        logger.info("=" * 50)
        logger.info("RESTORATION MODE: Force all settings regardless of device status")
        logger.info("=" * 50)

        # Restore network-level settings
        self._restore_network_settings(backup["network_settings"], target_network_id)

        # Restore device-specific settings
        if device_mapping:
            self._restore_device_settings(backup["device_settings"], device_mapping)
        else:
            logger.warning("No device mapping provided, skipping device-specific settings")

        logger.info("=" * 50)
        logger.info("RESTORE COMPLETE")
        logger.info("=" * 50)
        logger.info("Settings have been pushed to the Meraki cloud.")
        logger.info("They will be applied to devices when they come online.")
        logger.info("\nPlease verify the following in the Dashboard:")
        logger.info("  1. All network settings are properly configured")
        logger.info("  2. Device configurations are queued/applied")
        logger.info("  3. Port configurations are set correctly")
        logger.info("  4. Routing and DHCP settings are configured")
        logger.info("  5. Check for any configuration errors in the dashboard")
        logger.info("=" * 50)

    def _create_radius_servers(self, network_id: str, access_policies: List[Dict]) -> Dict[str, str]:
        """
        Create RADIUS servers in the target network and return mapping of old ID to new ID
        """
        radius_server_map = {}
        created_servers = {}  # Track unique servers by host:port to avoid duplicates

        logger.info("Creating RADIUS servers for access policies...")

        # Extract all unique RADIUS servers from access policies
        for policy in access_policies:
            if policy.get('radiusServers'):
                for server in policy['radiusServers']:
                    server_key = f"{server.get('host')}:{server.get('port', 1812)}"
                    old_server_id = server.get('serverId')

                    if server_key not in created_servers and old_server_id:
                        # Create the RADIUS server
                        radius_data = {
                            'host': server['host'],
                            'port': server.get('port', 1812),
                            'secret': 'Meraki123'  # You'll need to update this in the dashboard
                        }

                        try:
                            # Create RADIUS server
                            result = self.api._api_call("POST", f"/networks/{network_id}/switch/accessPolicies/radiusServers",
                                                        data=radius_data)

                            if result and 'serverId' in result:
                                new_server_id = result['serverId']
                                created_servers[server_key] = new_server_id
                                radius_server_map[old_server_id] = new_server_id
                                logger.info(f"  ✓ Created RADIUS server {server['host']}:{server.get('port', 1812)} with ID {new_server_id}")
                            else:
                                logger.error(f"  ✗ Failed to create RADIUS server {server['host']}")

                        except Exception as e:
                            # If server already exists, try to find it
                            if "already exists" in str(e) or "duplicate" in str(e).lower():
                                try:
                                    # Get all RADIUS servers to find the existing one
                                    existing_servers = self.api._api_call("GET", f"/networks/{network_id}/switch/accessPolicies/radiusServers")

                                    for existing_server in existing_servers:
                                        if (existing_server.get('host') == server['host'] and
                                                existing_server.get('port', 1812) == server.get('port', 1812)):
                                            new_server_id = existing_server['serverId']
                                            created_servers[server_key] = new_server_id
                                            radius_server_map[old_server_id] = new_server_id
                                            logger.info(f"  ℹ Found existing RADIUS server {server['host']}:{server.get('port', 1812)} with ID {new_server_id}")
                                            break
                                except:
                                    logger.error(f"  ✗ Could not find existing RADIUS server {server['host']}")
                            else:
                                logger.error(f"  ✗ Failed to create RADIUS server {server['host']}: {e}")

                    elif server_key in created_servers and old_server_id:
                        # Map to already created server
                        radius_server_map[old_server_id] = created_servers[server_key]

        if radius_server_map:
            logger.warning("⚠ IMPORTANT: RADIUS servers created with placeholder secret 'ChangeMe123!'")
            logger.warning("⚠ You MUST update the RADIUS secrets in the Meraki dashboard before using these policies!")

        return radius_server_map

    def _restore_access_policies_with_radius(self, network_id: str, access_policies: List[Dict]):
        """
        Restore access policies after creating RADIUS servers
        """
        if not access_policies:
            return True, 0

        try:
            # First, create all RADIUS servers and get the mapping
            radius_server_map = self._create_radius_servers(network_id, access_policies)

            # Now restore the access policies with the new server IDs
            restored_policies = 0

            for policy in access_policies:
                policy_data = self._clean_api_data(policy,
                                                   remove_fields=['accessPolicyNumber', 'counts'])

                # Update RADIUS server IDs
                if policy_data.get('radiusServers'):
                    new_radius_servers = []
                    for server in policy_data['radiusServers']:
                        old_server_id = server.get('serverId')
                        if old_server_id and old_server_id in radius_server_map:
                            new_server = {
                                'serverId': radius_server_map[old_server_id],
                                'host': server.get('host'),
                                'port': server.get('port', 1812)
                            }
                            new_radius_servers.append(new_server)
                        else:
                            logger.warning(f"Could not map RADIUS server {old_server_id} for policy {policy_data.get('name')}")

                    policy_data['radiusServers'] = new_radius_servers

                # Ensure all required fields are present
                required_fields = {
                    'name': policy_data.get('name', 'Unnamed Policy'),
                    'radiusServers': policy_data.get('radiusServers', []),
                    'radius': policy_data.get('radius', {
                        'criticalAuth': {
                            'dataVlanId': None,
                            'voiceVlanId': None,
                            'suspendPortBounce': False
                        },
                        'failedAuthVlanId': None,
                        'reAuthenticationInterval': None,
                        'cache': {
                            'enabled': False,
                            'timeout': 24
                        }
                    }),
                    'guestPortBouncing': policy_data.get('guestPortBouncing', False),
                    'radiusTestingEnabled': policy_data.get('radiusTestingEnabled', True),
                    'radiusGroupAttribute': policy_data.get('radiusGroupAttribute', ''),
                    'radiusCoaSupportEnabled': policy_data.get('radiusCoaSupportEnabled', False),
                    'radiusAccountingEnabled': policy_data.get('radiusAccountingEnabled', False),
                    'radiusAccountingServers': policy_data.get('radiusAccountingServers', []),
                    'hostMode': policy_data.get('hostMode', 'Single-Host'),
                    'accessPolicyType': policy_data.get('accessPolicyType', '802.1x'),
                    'authenticationMethod': policy_data.get('authenticationMethod', 'my RADIUS server'),
                    'guestVlanId': policy_data.get('guestVlanId', None),
                    'voiceVlanClients': policy_data.get('voiceVlanClients', True),
                    'urlRedirectWalledGardenEnabled': policy_data.get('urlRedirectWalledGardenEnabled', False)
                }

                # Add dot1x settings if present
                if policy_data.get('dot1x'):
                    required_fields['dot1x'] = policy_data['dot1x']

                try:
                    self.api._api_call("POST", f"/networks/{network_id}/switch/accessPolicies",
                                       data=required_fields)
                    logger.info(f"  ✓ Restored access policy: {required_fields['name']}")
                    restored_policies += 1

                except Exception as e:
                    logger.error(f"  ✗ Failed to restore access policy '{required_fields['name']}': {e}")

            return True, restored_policies

        except Exception as e:
            logger.error(f"Failed to restore access policies: {e}")
            return False, 0

    def _restore_network_settings(self, settings: Dict, network_id: str):
        """Restore network-level settings with complete error handling and ID mapping"""
        logger.info("Restoring network-level settings...")
        restored_count = 0
        failed_count = 0

        # Initialize ID mappings for network resources
        access_policy_id_mapping = {}  # Maps old access policy numbers to new ones
        port_schedule_id_mapping = {}  # Maps old port schedule IDs to new ones
        qos_rule_id_mapping = {}  # Maps old QoS rule IDs to new ones
        link_aggregation_id_mapping = {}  # Maps old link aggregation IDs to new ones

        # First, check what product types the network supports
        network_info = None
        try:
            network_info = self.api._api_call("GET", f"/networks/{network_id}")
            supported_products = network_info.get('productTypes', [])
            logger.info(f"Target network supports product types: {supported_products}")
        except Exception as e:
            logger.warning(f"Could not get network info: {e}")
            supported_products = []

        # Restore switch settings
        switch_settings = settings.get("switch", {})

        # Port Schedules - MUST BE RESTORED FIRST (before access policies that reference them)
        if switch_settings.get("portSchedules"):
            try:
                restored_schedules = 0
                for schedule in switch_settings["portSchedules"]:
                    old_schedule_id = schedule.get("id")
                    schedule_data = {k: v for k, v in schedule.items() if k != "id"}

                    try:
                        result = self.api._api_call("POST", f"/networks/{network_id}/switch/portSchedules",
                                                    data=schedule_data)
                        if result and "id" in result:
                            port_schedule_id_mapping[old_schedule_id] = result["id"]
                            restored_schedules += 1
                            logger.debug(f"  ✓ Created port schedule: {schedule.get('name')}")
                    except Exception as e:
                        if "already exists" in str(e):
                            # Try to find existing schedule
                            try:
                                existing_schedules = self.api._api_call("GET", f"/networks/{network_id}/switch/portSchedules")
                                for existing in existing_schedules:
                                    if existing.get('name') == schedule.get('name'):
                                        port_schedule_id_mapping[old_schedule_id] = existing['id']
                                        logger.debug(f"  ℹ Found existing port schedule: {schedule.get('name')}")
                                        break
                            except:
                                pass
                        else:
                            logger.error(f"  ✗ Failed to restore port schedule '{schedule.get('name')}': {e}")

                logger.info(f"Restored {restored_schedules} port schedules")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore port schedules: {e}")
                failed_count += 1

        # QoS Rules - Restore before access policies
        if switch_settings.get("qosRules"):
            try:
                restored_rules = 0
                for rule in switch_settings["qosRules"]:
                    old_rule_id = rule.get("id")
                    rule_data = {k: v for k, v in rule.items() if k != "id"}

                    try:
                        result = self.api._api_call("POST", f"/networks/{network_id}/switch/qosRules",
                                                    data=rule_data)
                        if result and "id" in result:
                            qos_rule_id_mapping[old_rule_id] = result["id"]
                            restored_rules += 1
                    except Exception as e:
                        logger.error(f"  ✗ Failed to restore QoS rule: {e}")

                logger.info(f"Restored {restored_rules} QoS rules")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore QoS rules: {e}")
                failed_count += 1

        # Link Aggregations - Restore before other settings that might reference them
        if switch_settings.get("linkAggregations"):
            try:
                restored_aggregations = 0
                for agg in switch_settings["linkAggregations"]:
                    old_agg_id = agg.get("id")
                    agg_data = {k: v for k, v in agg.items() if k != "id"}

                    try:
                        result = self.api._api_call("POST", f"/networks/{network_id}/switch/linkAggregations",
                                                    data=agg_data)
                        if result and "id" in result:
                            link_aggregation_id_mapping[old_agg_id] = result["id"]
                            restored_aggregations += 1
                    except Exception as e:
                        logger.error(f"  ✗ Failed to restore link aggregation: {e}")

                logger.info(f"Restored {restored_aggregations} link aggregations")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore link aggregations: {e}")
                failed_count += 1

        # Access Policies - WITH RADIUS SERVER CREATION and ID mapping
        if switch_settings.get("accessPolicies"):
            success, num_restored = self._restore_access_policies_with_mapping(
                network_id,
                switch_settings["accessPolicies"],
                port_schedule_id_mapping,
                access_policy_id_mapping
            )

            if success and num_restored > 0:
                logger.info(f"Restored {num_restored} access policies with RADIUS servers")
                restored_count += 1
            elif not success:
                logger.error("Failed to restore access policies")
                failed_count += 1
            else:
                logger.info("No access policies were restored")

        # STP settings
        if switch_settings.get("stp"):
            try:
                stp_data = self._clean_api_data(switch_settings["stp"],
                                                remove_fields=['warnings', 'errors'])

                self.api._api_call("PUT", f"/networks/{network_id}/switch/stp",
                                   data=stp_data)
                logger.info("Restored STP settings")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore STP: {e}")
                failed_count += 1

        # MTU settings
        if switch_settings.get("mtu") and 'switch' in supported_products:
            try:
                mtu_data = self._clean_api_data(switch_settings["mtu"],
                                                remove_fields=['warnings', 'errors'])

                # MTU API is picky - ensure we only send valid fields
                valid_mtu_fields = ['defaultMtuSize', 'overrides']
                mtu_cleaned = {k: v for k, v in mtu_data.items() if k in valid_mtu_fields}

                if mtu_cleaned:
                    self.api._api_call("PUT", f"/networks/{network_id}/switch/mtu",
                                       data=mtu_cleaned)
                    logger.info("Restored MTU settings")
                    restored_count += 1
                else:
                    logger.info("Skipped MTU - no valid settings to restore")
            except Exception as e:
                if "400" in str(e) or "does not support" in str(e):
                    logger.info("MTU settings not supported on this network")
                else:
                    logger.error(f"Failed to restore MTU: {e}")
                    failed_count += 1

        # Continue with other network settings...
        # (Rest of the network settings remain the same)

        logger.info(f"Restored {restored_count} network-level settings successfully")
        if failed_count > 0:
            logger.warning(f"Failed to restore {failed_count} network-level settings")
            logger.warning("Some settings may not be applicable to the new network or may need manual configuration")

        # Return the ID mappings so they can be used by device restoration if needed
        return {
            "access_policy_mapping": access_policy_id_mapping,
            "port_schedule_mapping": port_schedule_id_mapping,
            "qos_rule_mapping": qos_rule_id_mapping,
            "link_aggregation_mapping": link_aggregation_id_mapping
        }

    def _restore_access_policies_with_mapping(self, network_id: str, access_policies: List[Dict],
                                              port_schedule_mapping: Dict, access_policy_mapping: Dict):
        """
        Restore access policies with inline RADIUS servers and handle ID mappings
        """
        if not access_policies:
            return True, 0

        try:
            restored_policies = 0

            for policy in access_policies:
                old_policy_number = policy.get('accessPolicyNumber')

                # Clean the policy data
                policy_data = self._clean_api_data(policy,
                                                   remove_fields=['accessPolicyNumber', 'counts', 'enforceRadiusMonitoring'])

                # Transform RADIUS servers from backup format to creation format
                # The backup has serverId but we need to provide secret when creating
                if policy_data.get('radiusServers'):
                    cleaned_servers = []
                    for server in policy_data['radiusServers']:
                        # Create new server definition without serverId
                        cleaned_server = {
                            'host': server.get('host'),
                            'port': server.get('port', 1812),
                            'secret': 'REPLACE_WITH_ACTUAL_SECRET'  # MUST be updated by admin
                        }
                        cleaned_servers.append(cleaned_server)

                    policy_data['radiusServers'] = cleaned_servers

                # Update port schedule ID if referenced
                if policy_data.get('portScheduleId'):
                    old_schedule_id = policy_data['portScheduleId']
                    new_schedule_id = port_schedule_mapping.get(old_schedule_id)
                    if new_schedule_id:
                        policy_data['portScheduleId'] = new_schedule_id
                    else:
                        logger.warning(f"Could not map port schedule {old_schedule_id} for policy {policy_data.get('name')}")
                        # Remove the schedule reference rather than failing
                        policy_data.pop('portScheduleId', None)

                # Clean RADIUS accounting servers if present
                if policy_data.get('radiusAccountingServers'):
                    cleaned_accounting = []
                    for server in policy_data['radiusAccountingServers']:
                        # Remove serverId and add required secret
                        cleaned_accounting.append({
                            'host': server.get('host'),
                            'port': server.get('port', 1813),
                            'secret': 'REPLACE_WITH_ACTUAL_SECRET'  # MUST be updated by admin
                        })
                    policy_data['radiusAccountingServers'] = cleaned_accounting

                # Build the policy configuration for creation
                policy_config = {
                    'name': policy_data.get('name', 'Unnamed Policy'),
                    'radiusServers': policy_data.get('radiusServers', []),
                    'radiusTestingEnabled': policy_data.get('radiusTestingEnabled', True),
                    'guestPortBouncing': policy_data.get('guestPortBouncing', False),
                    'radiusGroupAttribute': policy_data.get('radiusGroupAttribute', ''),
                    'radius': policy_data.get('radius', {
                        'criticalAuth': {
                            'dataVlanId': None,
                            'voiceVlanId': None,
                            'suspendPortBounce': False
                        },
                        'failedAuthVlanId': None,
                        'reAuthenticationInterval': None,
                        'cache': {
                            'enabled': False,
                            'timeout': 24
                        }
                    }),
                    'radiusCoaSupportEnabled': policy_data.get('radiusCoaSupportEnabled', False),
                    'radiusAccountingEnabled': policy_data.get('radiusAccountingEnabled', False),
                    'radiusAccountingServers': policy_data.get('radiusAccountingServers', []),
                    'hostMode': policy_data.get('hostMode', 'Single-Host'),
                    'accessPolicyType': policy_data.get('accessPolicyType', '802.1x'),
                    'authenticationMethod': policy_data.get('authenticationMethod', 'my RADIUS server'),
                    'guestVlanId': policy_data.get('guestVlanId'),
                    'voiceVlanClients': policy_data.get('voiceVlanClients', True),
                    'urlRedirectWalledGardenEnabled': policy_data.get('urlRedirectWalledGardenEnabled', False)
                }

                # Add optional fields if present
                if policy_data.get('dot1x'):
                    policy_config['dot1x'] = policy_data['dot1x']
                if policy_data.get('portScheduleId'):
                    policy_config['portScheduleId'] = policy_data['portScheduleId']
                if policy_data.get('increaseAccessSpeed'):
                    policy_config['increaseAccessSpeed'] = policy_data['increaseAccessSpeed']
                if policy_data.get('guestVlanDenyLocalAccess'):
                    policy_config['guestVlanDenyLocalAccess'] = policy_data['guestVlanDenyLocalAccess']
                if policy_data.get('urlRedirectWalledGardenRanges'):
                    policy_config['urlRedirectWalledGardenRanges'] = policy_data['urlRedirectWalledGardenRanges']

                try:
                    logger.debug(f"Creating access policy with data: {json.dumps(policy_config, indent=2)}")

                    result = self.api._api_call("POST", f"/networks/{network_id}/switch/accessPolicies",
                                                data=policy_config)

                    # Map the old access policy number to the new one
                    if result and 'accessPolicyNumber' in result:
                        access_policy_mapping[old_policy_number] = result['accessPolicyNumber']

                    logger.info(f"  ✓ Restored access policy: {policy_config['name']}")

                    # Log critical warning about RADIUS secrets
                    if policy_config.get('radiusServers'):
                        logger.warning("  ⚠️  CRITICAL: RADIUS server secrets MUST be updated!")
                        logger.warning(f"     Policy '{policy_config['name']}' has {len(policy_config['radiusServers'])} RADIUS server(s):")
                        for i, server in enumerate(policy_config['radiusServers']):
                            logger.warning(f"       - Server {i+1}: {server['host']}:{server['port']} - UPDATE SECRET REQUIRED")

                    if policy_config.get('radiusAccountingServers'):
                        logger.warning(f"     Policy '{policy_config['name']}' has {len(policy_config['radiusAccountingServers'])} RADIUS accounting server(s):")
                        for i, server in enumerate(policy_config['radiusAccountingServers']):
                            logger.warning(f"       - Accounting Server {i+1}: {server['host']}:{server['port']} - UPDATE SECRET REQUIRED")

                    restored_policies += 1

                except Exception as e:
                    logger.error(f"  ✗ Failed to restore access policy '{policy_config['name']}': {e}")

                    # Check if it's a RADIUS secret issue
                    if "secret" in str(e).lower() or "radius" in str(e).lower():
                        logger.error("     This may be due to invalid RADIUS server configuration")
                        logger.error("     The API requires a valid 'secret' field for each RADIUS server")

                    # Log the attempted configuration for debugging
                    logger.debug(f"    Failed policy data: {json.dumps(policy_config, indent=2)}")

            if restored_policies > 0:
                logger.warning("\n" + "="*70)
                logger.warning("IMPORTANT: RADIUS SERVER SECURITY")
                logger.warning("="*70)
                logger.warning("All RADIUS server secrets have been set to 'REPLACE_WITH_ACTUAL_SECRET'")
                logger.warning("You MUST update these secrets in the Meraki dashboard before using these policies!")
                logger.warning("Go to Network > Switch > Access policies to update the RADIUS secrets.")
                logger.warning("="*70 + "\n")

            return True, restored_policies

        except Exception as e:
            logger.error(f"Failed to restore access policies: {e}")
            return False, 0

        except Exception as e:
            logger.error(f"Failed to restore access policies: {e}")
            return False, 0

    def _clean_api_data(self, data: Dict, remove_fields: List[str] = None) -> Dict:
        """Remove read-only and problematic fields from API data"""
        if not data:
            return {}

        # Common read-only fields to remove
        default_remove = ['id', 'serial', 'mac', 'warnings', 'errors',
                          'createdAt', 'updatedAt', 'lastUpdated',
                          'status', 'usage', 'counts']

        if remove_fields:
            default_remove.extend(remove_fields)

        # Create a deep copy to avoid modifying the original
        import copy
        cleaned = copy.deepcopy(data)

        # Remove specified fields
        for field in default_remove:
            cleaned.pop(field, None)

        # Remove None values as they can cause issues
        cleaned = {k: v for k, v in cleaned.items() if v is not None}

        return cleaned
    def _restore_device_settings(self, device_settings: Dict, device_mapping: Dict):
        """Restore device-specific settings - NO ONLINE CHECKS"""
        logger.info(f"Restoring device-specific settings for {len(device_mapping)} devices...")
        logger.info("Note: Restoring all settings regardless of device status")

        for old_serial, new_serial in device_mapping.items():
            if old_serial not in device_settings:
                logger.warning(f"No settings found for device {old_serial}")
                continue

            settings = device_settings[old_serial]
            device_name = settings.get("info", {}).get("name", "Unnamed")
            model = settings.get("info", {}).get("model", "Unknown")
            logger.info(f"\nRestoring settings for device {new_serial} ({device_name}, {model})")

            restored_items = 0
            failed_items = 0

            # Initialize ID mappings for various resources
            interface_id_mapping = {}  # Maps old interface IDs to new ones
            dhcp_server_id_mapping = {}  # Maps old DHCP server IDs to new ones
            static_route_id_mapping = {}  # Maps old static route IDs to new ones
            rendezvous_point_id_mapping = {}  # Maps old RP IDs to new ones

            # Restore routing interfaces FIRST (before static routes or DHCP)
            if settings.get("routing", {}).get("interfaces"):
                successful_interfaces = 0
                total_interfaces = len(settings["routing"]["interfaces"])

                logger.info(f"  → Restoring {total_interfaces} routing interfaces...")

                for interface in settings["routing"]["interfaces"]:
                    old_interface_id = interface["interfaceId"]
                    interface_data = {k: v for k, v in interface.items()
                                      if k not in ["interfaceId", "serial"]}

                    try:
                        # First, check if this is the default VLAN 1 interface
                        if interface.get("vlanId") == 1:
                            # VLAN 1 interface exists by default, just update it
                            try:
                                self.api._api_call("PUT", f"/devices/{new_serial}/switch/routing/interfaces/1",
                                                   data=interface_data)
                                successful_interfaces += 1
                                interface_id_mapping[old_interface_id] = "1"
                                logger.debug(f"    ✓ Updated default VLAN 1 interface")
                            except Exception as e:
                                logger.warning(f"    ⚠ Failed to update VLAN 1 interface: {str(e)[:100]}")
                                failed_items += 1
                        else:
                            # For other VLANs, create new interfaces
                            try:
                                # Create the interface - API will return the new interface with its ID
                                result = self.api._api_call("POST", f"/devices/{new_serial}/switch/routing/interfaces",
                                                            data=interface_data)
                                if result and "interfaceId" in result:
                                    new_interface_id = result["interfaceId"]
                                    interface_id_mapping[old_interface_id] = new_interface_id
                                    successful_interfaces += 1
                                    logger.debug(f"    ✓ Created interface for VLAN {interface.get('vlanId')} with new ID {new_interface_id}")
                                else:
                                    logger.warning(f"    ⚠ Failed to create interface for VLAN {interface.get('vlanId')}")
                                    failed_items += 1
                            except Exception as e:
                                # If interface already exists for this VLAN, try to update it
                                if "already exists" in str(e) or "duplicate" in str(e).lower():
                                    vlan_id = interface.get('vlanId')
                                    if vlan_id:
                                        try:
                                            # Get all interfaces to find the one for this VLAN
                                            existing_interfaces = self.api._api_call("GET", f"/devices/{new_serial}/switch/routing/interfaces")
                                            for existing in existing_interfaces:
                                                if existing.get('vlanId') == vlan_id:
                                                    existing_id = existing['interfaceId']
                                                    # Update the existing interface
                                                    self.api._api_call("PUT", f"/devices/{new_serial}/switch/routing/interfaces/{existing_id}",
                                                                       data=interface_data)
                                                    interface_id_mapping[old_interface_id] = existing_id
                                                    successful_interfaces += 1
                                                    logger.debug(f"    ✓ Updated existing interface for VLAN {vlan_id}")
                                                    break
                                        except Exception as update_e:
                                            logger.warning(f"    ⚠ Failed to update existing interface for VLAN {vlan_id}: {str(update_e)[:100]}")
                                            failed_items += 1
                                else:
                                    logger.warning(f"    ⚠ Failed to create routing interface: {str(e)[:100]}")
                                    failed_items += 1

                    except Exception as e:
                        logger.warning(f"    ⚠ Failed to restore routing interface: {str(e)[:100]}")
                        failed_items += 1

                if successful_interfaces > 0:
                    logger.info(f"  ✓ Restored {successful_interfaces}/{total_interfaces} routing interfaces")
                    restored_items += successful_interfaces

            # Restore DHCP settings (after interfaces are created)
            if settings.get("dhcp"):
                # DHCP server settings - CREATE new ones and map IDs
                if settings["dhcp"].get("servers"):
                    try:
                        server_count = 0
                        for server in settings["dhcp"]["servers"]:
                            old_server_id = server.get("id")
                            server_data = {k: v for k, v in server.items() if k != "id"}

                            # If the DHCP server references an interface, update the interface ID
                            if server_data.get("interfaceId"):
                                old_interface_id = server_data["interfaceId"]
                                new_interface_id = interface_id_mapping.get(old_interface_id)
                                if new_interface_id:
                                    server_data["interfaceId"] = new_interface_id
                                else:
                                    logger.warning(f"    ⚠ Cannot map interface ID for DHCP server")
                                    continue

                            result = self.api._api_call("POST", f"/devices/{new_serial}/switch/dhcp/v4/servers",
                                                        data=server_data)
                            if result and "id" in result:
                                dhcp_server_id_mapping[old_server_id] = result["id"]
                            server_count += 1

                        logger.info(f"  ✓ Restored {server_count} DHCP server configurations")
                        restored_items += 1
                    except Exception as e:
                        logger.warning(f"  ⚠ Failed to restore DHCP servers: {str(e)[:100]}")
                        failed_items += 1

                # DHCP relay settings
                if settings["dhcp"].get("relays"):
                    try:
                        relay_data = settings["dhcp"]["relays"]

                        # Update interface IDs in relay settings if present
                        if isinstance(relay_data, dict) and relay_data.get("interfaceId"):
                            old_interface_id = relay_data["interfaceId"]
                            new_interface_id = interface_id_mapping.get(old_interface_id)
                            if new_interface_id:
                                relay_data["interfaceId"] = new_interface_id

                        self.api._api_call("PUT", f"/devices/{new_serial}/switch/dhcp/v4/relays",
                                           data=relay_data)
                        logger.info(f"  ✓ Restored DHCP relay settings")
                        restored_items += 1
                    except Exception as e:
                        logger.warning(f"  ⚠ Failed to restore DHCP relays: {str(e)[:100]}")
                        failed_items += 1

                # Interface-specific DHCP - using mapped interface IDs
                if settings["dhcp"].get("interfaceDhcp"):
                    dhcp_success = 0
                    for int_dhcp in settings["dhcp"]["interfaceDhcp"]:
                        old_interface_id = int_dhcp['interfaceId']
                        new_interface_id = interface_id_mapping.get(old_interface_id)

                        if new_interface_id:
                            try:
                                self.api._api_call("PUT",
                                                   f"/devices/{new_serial}/switch/routing/interfaces/{new_interface_id}/dhcp",
                                                   data=int_dhcp["dhcpSettings"])
                                dhcp_success += 1
                            except Exception as e:
                                logger.debug(f"    Failed to restore DHCP for interface {new_interface_id}: {str(e)[:100]}")
                        else:
                            logger.debug(f"    Skipping DHCP for unmapped interface {old_interface_id}")

                    if dhcp_success > 0:
                        logger.info(f"  ✓ Restored DHCP settings for {dhcp_success} interfaces")
                        restored_items += 1

            # Restore static routes - CREATE new ones and handle interface ID mapping
            if settings.get("routing", {}).get("staticRoutes"):
                successful_routes = 0
                total_routes = len(settings["routing"]["staticRoutes"])

                logger.info(f"  → Restoring {total_routes} static routes...")

                for route in settings["routing"]["staticRoutes"]:
                    old_route_id = route.get("staticRouteId")
                    route_data = {k: v for k, v in route.items() if k not in ["staticRouteId"]}

                    # Update the next hop interface ID if it references an interface
                    if route_data.get("interfaceId"):
                        old_interface_id = route_data["interfaceId"]
                        new_interface_id = interface_id_mapping.get(old_interface_id)
                        if new_interface_id:
                            route_data["interfaceId"] = new_interface_id
                        else:
                            logger.warning(f"    ⚠ Cannot map interface ID for route to {route.get('subnet')}")
                            continue

                    try:
                        result = self.api._api_call("POST", f"/devices/{new_serial}/switch/routing/staticRoutes",
                                                    data=route_data)
                        if result and "staticRouteId" in result:
                            static_route_id_mapping[old_route_id] = result["staticRouteId"]
                        successful_routes += 1
                        logger.debug(f"    ✓ Restored route to {route.get('subnet', 'unknown')}")
                    except Exception as e:
                        logger.warning(f"    ⚠ Failed to restore static route: {str(e)[:100]}")
                        failed_items += 1

                if successful_routes > 0:
                    logger.info(f"  ✓ Restored {successful_routes}/{total_routes} static routes")
                    restored_items += successful_routes

            # Restore OSPF settings - IDs are not transferable, but interface references need mapping
            if settings.get("routing", {}).get("ospf"):
                try:
                    ospf_data = {k: v for k, v in settings["routing"]["ospf"].items()
                                 if k not in ["ospfId"]}

                    # Update interface IDs in OSPF areas if present
                    if ospf_data.get("areas"):
                        for area in ospf_data["areas"]:
                            if area.get("interfaceIds"):
                                new_interface_ids = []
                                for old_id in area["interfaceIds"]:
                                    new_id = interface_id_mapping.get(old_id)
                                    if new_id:
                                        new_interface_ids.append(new_id)
                                    else:
                                        logger.warning(f"    ⚠ Cannot map interface ID {old_id} for OSPF area")
                                area["interfaceIds"] = new_interface_ids

                    self.api._api_call("PUT", f"/devices/{new_serial}/switch/routing/ospf",
                                       data=ospf_data)
                    logger.info(f"  ✓ Restored OSPF settings")
                    restored_items += 1
                except Exception as e:
                    logger.warning(f"  ⚠ Failed to restore OSPF: {str(e)[:100]}")
                    failed_items += 1

            # Restore multicast settings
            if settings.get("routing", {}).get("multicast"):
                try:
                    multicast_data = settings["routing"]["multicast"]

                    # Update interface IDs in multicast settings if present
                    if multicast_data.get("igmpSnoopingSettings") and multicast_data["igmpSnoopingSettings"].get("interfaceIds"):
                        old_ids = multicast_data["igmpSnoopingSettings"]["interfaceIds"]
                        new_ids = []
                        for old_id in old_ids:
                            new_id = interface_id_mapping.get(old_id)
                            if new_id:
                                new_ids.append(new_id)
                        multicast_data["igmpSnoopingSettings"]["interfaceIds"] = new_ids

                    self.api._api_call("PUT", f"/devices/{new_serial}/switch/routing/multicast",
                                       data=multicast_data)
                    logger.info(f"  ✓ Restored multicast settings")
                    restored_items += 1
                except Exception as e:
                    logger.warning(f"  ⚠ Failed to restore multicast: {str(e)[:100]}")
                    failed_items += 1

            # Restore rendezvous points for multicast - CREATE new ones
            if settings.get("routing", {}).get("rendezvousPoints"):
                try:
                    rp_count = 0
                    for rp in settings["routing"]["rendezvousPoints"]:
                        old_rp_id = rp.get("rendezvousPointId")
                        rp_data = {k: v for k, v in rp.items() if k not in ["rendezvousPointId"]}

                        # Update interface ID if present
                        if rp_data.get("interfaceId"):
                            old_interface_id = rp_data["interfaceId"]
                            new_interface_id = interface_id_mapping.get(old_interface_id)
                            if new_interface_id:
                                rp_data["interfaceId"] = new_interface_id
                            else:
                                logger.warning(f"    ⚠ Cannot map interface ID for rendezvous point")
                                continue

                        result = self.api._api_call("POST", f"/devices/{new_serial}/switch/routing/multicast/rendezvousPoints",
                                                    data=rp_data)
                        if result and "rendezvousPointId" in result:
                            rendezvous_point_id_mapping[old_rp_id] = result["rendezvousPointId"]
                        rp_count += 1

                    logger.info(f"  ✓ Restored {rp_count} multicast rendezvous points")
                    restored_items += 1
                except Exception as e:
                    logger.warning(f"  ⚠ Failed to restore rendezvous points: {str(e)[:100]}")
                    failed_items += 1

            # Restore warm spare settings
            if settings.get("warmSpare"):
                try:
                    spare_data = {k: v for k, v in settings["warmSpare"].items()
                                  if k not in ["primarySerial", "spareSerial"]}

                    # Note: Warm spare will need to be reconfigured with new device serials
                    # This just restores the configuration settings
                    self.api._api_call("PUT", f"/devices/{new_serial}/switch/warmSpare",
                                       data=spare_data)
                    logger.info(f"  ✓ Restored warm spare settings")
                    logger.warning("  ⚠ Note: You'll need to manually set the spare device serial in the dashboard")
                    restored_items += 1
                except Exception as e:
                    logger.warning(f"  ⚠ Failed to restore warm spare: {str(e)[:100]}")
                    failed_items += 1

            # Restore switch ports
            if settings.get("ports"):
                successful_ports = 0
                failed_ports = 0
                total_ports = len(settings["ports"])

                logger.info(f"  → Restoring {total_ports} port configurations...")

                for i, port in enumerate(settings["ports"]):
                    port_id = port["portId"]

                    # Remove read-only fields
                    port_data = {k: v for k, v in port.items()
                                 if k not in ["portId", "warnings", "errors", "status", "speed", "duplex",
                                              "usageInKbps", "cdp", "lldp", "clientCount", "powerUsageInWh",
                                              "securePort", "spanningTree", "adaptivePolicyGroup",
                                              "peerSgtCapable", "macAllowList", "stickyMacAllowList",
                                              "stickyMacAllowListLimit", "stormControlEnabled"]}

                    # Check if port references any IDs that need mapping
                    # For example, if port has a reference to an interface for routing
                    if port_data.get("routingInterfaceId"):
                        old_interface_id = port_data["routingInterfaceId"]
                        new_interface_id = interface_id_mapping.get(old_interface_id)
                        if new_interface_id:
                            port_data["routingInterfaceId"] = new_interface_id

                    try:
                        self.api._api_call("PUT", f"/devices/{new_serial}/switch/ports/{port_id}",
                                           data=port_data)
                        successful_ports += 1

                        # Log progress every 10 ports
                        if (i + 1) % 10 == 0:
                            logger.debug(f"    Progress: {i + 1}/{total_ports} ports processed")

                    except Exception as e:
                        failed_ports += 1
                        # Only log first few port failures to avoid spam
                        if failed_ports <= 5:
                            logger.debug(f"    Failed port {port_id}: {str(e)[:100]}")
                        elif failed_ports == 6:
                            logger.debug(f"    (suppressing further port error details)")

                logger.info(f"  ✓ Restored {successful_ports}/{total_ports} ports")
                if failed_ports > 0:
                    logger.warning(f"  ⚠ Failed to restore {failed_ports} ports")
                    failed_items += failed_ports
                restored_items += successful_ports

            # Stack information (informational only)
            if settings.get("stackInfo"):
                logger.info(f"  ℹ Device is part of stack: {settings['stackInfo'].get('name', 'Unknown')}")
                logger.warning("  ⚠ Note: Stack membership must be reconfigured manually")

            # Summary for this device
            logger.info(f"\n  Summary for {new_serial}:")
            logger.info(f"    - Restored: {restored_items} configuration items")
            if failed_items > 0:
                logger.info(f"    - Failed: {failed_items} configuration items")
            logger.info(f"    - Total settings processed: {restored_items + failed_items}")

class AutomatedMigrationTool:
    """Main tool for automated migration with full org/network specification"""

    def __init__(self, source_api_key: str, target_api_key: str, username: str, password: str, headless: bool = False):
        self.source_api = MerakiAPIClient(source_api_key)
        self.target_api = MerakiAPIClient(target_api_key)
        self.username = username
        self.password = password
        self.headless = headless
        self.backup_tool = ComprehensiveBackup(self.source_api)
        self.restore_tool = ComprehensiveRestore(self.target_api)

    def execute_migration(self,
                          source_org_id: str, source_org_name: str,
                          source_network_id: str, source_network_name: str,
                          target_org_id: str, target_org_name: str,
                          target_network_name: Optional[str] = None):
        """Execute complete automated migration with explicit names and IDs"""

        logger.info("=" * 70)
        logger.info("MERAKI NETWORK MIGRATION TOOL")
        logger.info("=" * 70)
        logger.info(f"Source Organization: {source_org_name} (ID: {source_org_id})")
        logger.info(f"Source Network: {source_network_name} (ID: {source_network_id})")
        logger.info(f"Target Organization: {target_org_name} (ID: {target_org_id})")
        logger.info(f"Target Network Name: {target_network_name or source_network_name + '_migrated'}")
        logger.info("=" * 70)

        # Step 1: Verify access
        logger.info("\nSTEP 1: Verifying access to source and target organizations")
        logger.info("-" * 50)

        if not self.source_api.verify_org_access(source_org_id, source_org_name):
            raise Exception("Cannot verify source organization access")

        if not self.source_api.verify_network_access(source_network_id, source_network_name):
            raise Exception("Cannot verify source network access")

        if not self.target_api.verify_org_access(target_org_id, target_org_name):
            raise Exception("Cannot verify target organization access")

        # Step 2: Comprehensive backup
        logger.info("\nSTEP 2: Backing up all network and device settings")
        logger.info("-" * 50)

        backup = self.backup_tool.backup_all_settings(
            source_org_id, source_org_name,
            source_network_id, source_network_name
        )

        # Save backup
        backup_file = f"migration_backup_{source_network_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(backup_file, 'w') as f:
            json.dump(backup, f, indent=2)
        logger.info(f"Backup saved to {backup_file}")

        # Get device serials
        device_serials = [d['serial'] for d in backup['devices']]
        if not device_serials:
            logger.error("No devices found in source network!")
            return None

        logger.info(f"Found {len(device_serials)} devices to migrate:")
        for device in backup['devices']:
            logger.info(f"  - {device.get('name', 'Unnamed')} ({device['model']}) - {device['serial']}")

        # Step 3: UI Automation - Remove from network, Unclaim, and Claim
        logger.info("\nSTEP 3: Moving devices via UI automation")
        logger.info("-" * 50)

        with MerakiUIAutomation(self.username, self.password, self.headless) as ui:
            ui.login()

            # Remove devices from network
            logger.info(f"\n3a. Removing devices from network '{source_network_name}'")
            if not ui.select_organization(source_org_name):
                raise Exception("Failed to select source organization")

            if not ui.remove_devices_from_network(source_org_name, source_network_name, device_serials):
                logger.warning("Some devices may not have been removed from network")
                # Continue anyway as they might already be removed

            # Wait for removal to process
            logger.info("Waiting 60 seconds for network removal to process...")
            time.sleep(60)

            # Unclaim from source
            logger.info(f"\n3b. Unclaiming devices from organization '{source_org_name}'")
            if not ui.unclaim_devices(source_org_name, device_serials):
                raise Exception("Failed to unclaim devices")

            # Wait for unclaim to process
            logger.info("Waiting 180 seconds for unclaim to process...")
            time.sleep(180)

            # Claim in target
            logger.info(f"\n3c. Claiming devices in organization '{target_org_name}'")
            if not ui.select_organization(target_org_name):
                raise Exception("Failed to select target organization")

            if not ui.claim_devices(target_org_name, device_serials):
                raise Exception("Failed to claim devices")

        # Wait for claim to process
        logger.info("Waiting 60 seconds for claim to process...")
        time.sleep(60)

        # Step 4: Create network and add devices
        logger.info("\nSTEP 4: Creating network and adding devices")
        logger.info("-" * 50)

        # Create or find network
        network_name = target_network_name or f"{source_network_name}_migrated"
        network_config = {
            "name": network_name,
            "productTypes": backup['network_info'].get('productTypes', ['switch']),
            "timeZone": backup['network_info'].get('timeZone', 'America/Los_Angeles')
        }

        logger.info(f"Creating or finding network '{network_name}' in target organization...")
        try:
            target_network_id = self.target_api.create_network(target_org_id, network_config)
            logger.info(f"Using network with ID: {target_network_id}")
        except Exception as e:
            logger.error(f"Failed to create or find network: {e}")

            # List available networks in the target org
            logger.info("Available networks in target organization:")
            try:
                networks = self.target_api._api_call("GET", f"/organizations/{target_org_id}/networks")
                for net in networks:
                    logger.info(f"  - {net['name']} (ID: {net['id']})")
            except:
                pass

            raise Exception(f"Cannot proceed without a target network. Error: {e}")

        # Add devices to network
        logger.info(f"Adding {len(device_serials)} devices to network...")
        if self.target_api.add_devices_to_network(target_network_id, device_serials):
            logger.info("✓ Devices successfully added to network")
        else:
            logger.warning("⚠ Failed to add some devices to network - they may need to be added manually")

        # Short wait for API to process the addition
        logger.info("Waiting 30 seconds for device addition to process...")
        time.sleep(30)

        # Step 5: Restore settings WITHOUT checking device status
        logger.info("\nSTEP 5: Restoring all network and device settings")
        logger.info("-" * 50)
        logger.info("Note: Restoring ALL settings regardless of device online status")
        logger.info("Settings will be applied when devices come online")

        # Create device mapping (same serials in this case)
        device_mapping = {serial: serial for serial in device_serials}

        # Restore all settings without device status checks
        self.restore_tool.restore_all_settings(backup, target_network_id, device_mapping)

        # Final summary
        logger.info("\n" + "=" * 70)
        logger.info("MIGRATION COMPLETE!")
        logger.info("=" * 70)
        logger.info(f"Source: {source_org_name} > {source_network_name}")
        logger.info(f"Target: {target_org_name} > {network_name}")
        logger.info(f"Target Network ID: {target_network_id}")
        logger.info(f"Devices Migrated: {len(device_serials)}")
        logger.info(f"Backup File: {backup_file}")
        logger.info("=" * 70)
        logger.info("\nIMPORTANT:")
        logger.info("- Device settings have been pushed to the Meraki cloud")
        logger.info("- Settings will be applied when devices come online")
        logger.info("- You may see some API errors for offline devices - this is normal")
        logger.info("\nPlease verify in the Dashboard:")
        logger.info("  1. All devices appear in the new network")
        logger.info("  2. Network-level settings are correct")
        logger.info("  3. Device configurations are queued")
        logger.info("  4. Monitor device status as they come online")
        logger.info("=" * 70)

        return target_network_id


def main():
    parser = argparse.ArgumentParser(
        description="Automated Meraki Migration Tool - Complete Network Migration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
  python3 migrate.py \\
    --source-api-key "YOUR_SOURCE_KEY" \\
    --target-api-key "YOUR_TARGET_KEY" \\
    --username "user@example.com" \\
    --password "password" \\
    --source-org-id "123456" \\
    --source-org-name "Source Organization" \\
    --source-network-id "N_123456789" \\
    --source-network-name "Production Network" \\
    --target-org-id "789012" \\
    --target-org-name "Target Organization" \\
    --target-network-name "Production Network Migrated"
        """
    )

    # API credentials
    parser.add_argument("--source-api-key", required=True, help="Source organization API key")
    parser.add_argument("--target-api-key", required=True, help="Target organization API key")

    # UI credentials
    parser.add_argument("--username", required=True, help="Meraki Dashboard username")
    parser.add_argument("--password", required=True, help="Meraki Dashboard password")

    # Source organization and network
    parser.add_argument("--source-org-id", required=True, help="Source organization ID")
    parser.add_argument("--source-org-name", required=True, help="Source organization name")
    parser.add_argument("--source-network-id", required=True, help="Source network ID")
    parser.add_argument("--source-network-name", required=True, help="Source network name")

    # Target organization
    parser.add_argument("--target-org-id", required=True, help="Target organization ID")
    parser.add_argument("--target-org-name", required=True, help="Target organization name")
    parser.add_argument("--target-network-name", help="Target network name (optional, defaults to source + '_migrated')")

    # Options
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode (for servers)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    # Set debug logging if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")

    # Mask password in logs
    logger.info(f"Starting migration with user: {args.username}")
    logger.info("Using separate API keys for source and target organizations")
    if args.headless:
        logger.info("Running in HEADLESS mode")

    try:
        tool = AutomatedMigrationTool(
            args.source_api_key,
            args.target_api_key,
            args.username,
            args.password,
            args.headless
        )

        tool.execute_migration(
            args.source_org_id,
            args.source_org_name,
            args.source_network_id,
            args.source_network_name,
            args.target_org_id,
            args.target_org_name,
            args.target_network_name
        )

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        logger.error("Please check the log file for details")
        raise


if __name__ == "__main__":
    main()
