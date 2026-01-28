"""
Scanner diagnostic utility to enumerate all available WIA properties.

This module helps discover all available scanner settings that can be
adjusted for optimal card scanning.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Known WIA Property IDs with descriptions
WIA_PROPERTY_NAMES = {
    # Device Properties
    2: "Device ID",
    3: "Device Name",
    4: "Device Type",
    5: "Port Name",
    6: "Device Description",
    7: "Manufacturer",

    # Item Properties
    4098: "Item Name",
    4099: "Full Item Name",
    4100: "Item Time Stamp",
    4101: "Item Flags",
    4102: "Access Rights",
    4103: "Data Type",
    4104: "Bits Per Pixel",
    4105: "Preferred Format",
    4106: "Format",
    4107: "Compression",
    4108: "Media Type",
    4109: "Channels Per Pixel",
    4110: "Bits Per Channel",
    4111: "Planar",
    4112: "Pixels Per Line",
    4113: "Bytes Per Line",
    4114: "Number of Lines",
    4115: "Gamma Curves",
    4116: "Item Size",
    4117: "Color Profiles",
    4118: "Min Buffer Size",
    4119: "Buffer Size",
    4120: "Region Type",
    4121: "Color Profile Name",
    4122: "Application Color Profile",
    4123: "Thumbnail Data",
    4124: "Thumbnail Width",
    4125: "Thumbnail Height",
    4126: "Audio Available",
    4127: "Audio Format",
    4128: "Audio Data",
    4129: "Sequences",
    4130: "Sequence Num",
    4131: "Time Delay",
    4132: "Flash Mode",
    4133: "Focus Mode",
    4134: "Exposure Mode",
    4135: "Exposure Compensation",
    4136: "Lamp Timeout",
    4137: "Preview",

    # Scanner Properties
    3074: "Document Handling Capabilities",
    3075: "Document Handling Status",
    3076: "Document Handling Select",
    3078: "Bed Width",
    3079: "Bed Height",
    3086: "Sheet Feeder Registration",
    3087: "Horizontal Sheet Feed Size",
    3088: "Document Handling Select (Alt)",
    3089: "Vertical Sheet Feed Size",
    3090: "Pages",
    3091: "Page Size",
    3092: "Page Width",
    3093: "Page Height",
    3094: "Preview Type",
    3095: "Auto Deskew",
    3096: "Pages (Alt)",
    3097: "Orientation",
    3098: "Rotation",
    3099: "Mirror",
    3100: "Auto Crop",
    3101: "Photo Metric Interpretation",
    3102: "Film Scan Mode",
    3103: "Lamp Warmup Time",

    # Image Processing Properties
    6146: "Current Intent",
    6147: "Horizontal Resolution",
    6148: "Vertical Resolution",
    6149: "Horizontal Start Position",
    6150: "Vertical Start Position",
    6151: "Horizontal Extent",
    6152: "Vertical Extent",
    6153: "Photometric Interpretation",
    6154: "Brightness",
    6155: "Contrast",
    6156: "Threshold",
    6157: "Invert",
    6158: "Lamp Warmup Time",
    6159: "Feeder Control",
    6160: "Manual Feed Mode",  # This could help with card feeding!
    6161: "Document Handling Capacity",
    6162: "Document Handling Pages",
    6163: "Page Size",
    6164: "Page Width",
    6165: "Page Height",
    6166: "Multi Feed",
    6167: "Multi Feed Sensitivity",
    6168: "Feed Alignment",
    6169: "Max Horizontal Scan Size",
    6170: "Max Vertical Scan Size",
    6171: "Min Horizontal Scan Size",
    6172: "Min Vertical Scan Size",
    6173: "Optical Horizontal Resolution",
    6174: "Optical Vertical Resolution",
    6175: "Endorser Characters",
    6176: "Endorser String",
    6177: "Scan Ahead",
    6178: "Scan Ahead Capacity",
    6179: "Feeder Alignment",
    6180: "Feeder Order",
    6181: "Film Scan Mode",
    6182: "Lamp",
    6183: "Lamp Warmup Time",
    6184: "Auto Scan",
    6185: "Double Feed Detection",
    6186: "Double Feed Detect Sensitivity",
    6187: "Double Feed Detect Response",
    6188: "Barcode Detector",
    6189: "Patch Code Detector",

    # Additional common properties
    5001: "Firmware Version",
    5003: "Serial Number",
}

# Document handling capability flags
DOC_HANDLING_CAPS = {
    0x01: "FEEDER",
    0x02: "FLATBED",
    0x04: "DUPLEX",
    0x08: "FRONT_FIRST",
    0x10: "BACK_FIRST",
    0x20: "FRONT_ONLY",
    0x40: "BACK_ONLY",
    0x80: "NEXT_PAGE",
    0x100: "PREFEED",
    0x200: "AUTO_ADVANCE",
    0x400: "ENDORSED",
    0x800: "ADVANCED_DUPLEX",
    0x1000: "DETECT_FLAT",
    0x2000: "DETECT_SCAN",
    0x4000: "DETECT_FEED",
    0x8000: "DETECT_DUP",
}

# Data types
DATA_TYPES = {
    0: "Threshold (B&W)",
    1: "Dither",
    2: "Grayscale",
    3: "Color",
    4: "Text",
    5: "Custom",
}


def decode_doc_handling(value: int) -> List[str]:
    """Decode document handling capability flags."""
    capabilities = []
    for flag, name in DOC_HANDLING_CAPS.items():
        if value & flag:
            capabilities.append(name)
    return capabilities


class WIADiagnostic:
    """Diagnostic utility for enumerating WIA scanner properties."""

    def __init__(self):
        self._wia_manager = None
        self._device = None

    def _init_wia(self):
        """Initialize WIA COM interface."""
        if self._wia_manager is not None:
            return

        try:
            import win32com.client
            self._wia_manager = win32com.client.Dispatch("WIA.DeviceManager")
        except ImportError:
            raise RuntimeError("pywin32 is not installed")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize WIA: {e}")

    def list_scanners(self) -> List[Dict[str, Any]]:
        """List all available scanners with basic info."""
        self._init_wia()

        scanners = []
        for i in range(1, self._wia_manager.DeviceInfos.Count + 1):
            device_info = self._wia_manager.DeviceInfos.Item(i)
            if device_info.Type == 1:  # Scanner
                scanner = {
                    "index": i,
                    "device_id": device_info.DeviceID,
                    "properties": {}
                }

                # Get device info properties
                for j in range(1, device_info.Properties.Count + 1):
                    prop = device_info.Properties.Item(j)
                    scanner["properties"][prop.Name] = {
                        "id": prop.PropertyID,
                        "value": prop.Value,
                        "type": prop.Type,
                    }

                scanners.append(scanner)

        return scanners

    def connect_scanner(self, device_id: Optional[str] = None) -> None:
        """Connect to a scanner."""
        self._init_wia()

        for i in range(1, self._wia_manager.DeviceInfos.Count + 1):
            device_info = self._wia_manager.DeviceInfos.Item(i)
            if device_info.Type == 1:  # Scanner
                if device_id is None or device_info.DeviceID == device_id:
                    # Check if it's a Fujitsu
                    try:
                        for j in range(1, device_info.Properties.Count + 1):
                            prop = device_info.Properties.Item(j)
                            if "fujitsu" in str(prop.Value).lower():
                                self._device = device_info.Connect()
                                return
                        # If no Fujitsu found yet, connect to first/specified scanner
                        if device_id is not None:
                            self._device = device_info.Connect()
                            return
                    except:
                        pass

        # Connect to first scanner found if no Fujitsu
        for i in range(1, self._wia_manager.DeviceInfos.Count + 1):
            device_info = self._wia_manager.DeviceInfos.Item(i)
            if device_info.Type == 1:
                self._device = device_info.Connect()
                return

        raise RuntimeError("No scanner found")

    def get_device_properties(self) -> Dict[str, Any]:
        """Get all device-level properties."""
        if self._device is None:
            raise RuntimeError("Not connected to scanner")

        properties = {}
        props = self._device.Properties

        for i in range(1, props.Count + 1):
            prop = props.Item(i)
            prop_name = WIA_PROPERTY_NAMES.get(prop.PropertyID, f"Unknown_{prop.PropertyID}")

            try:
                value = prop.Value

                # Try to decode known flag values
                if prop.PropertyID in (3074, 3075, 3076, 3088):
                    decoded = decode_doc_handling(value)
                    properties[prop_name] = {
                        "id": prop.PropertyID,
                        "value": value,
                        "decoded": decoded,
                        "type": prop.Type,
                        "is_readonly": prop.IsReadOnly,
                    }
                elif prop.PropertyID == 4103:  # Data Type
                    properties[prop_name] = {
                        "id": prop.PropertyID,
                        "value": value,
                        "decoded": DATA_TYPES.get(value, f"Unknown ({value})"),
                        "type": prop.Type,
                        "is_readonly": prop.IsReadOnly,
                    }
                else:
                    properties[prop_name] = {
                        "id": prop.PropertyID,
                        "value": value,
                        "type": prop.Type,
                        "is_readonly": prop.IsReadOnly,
                    }

                # Try to get valid values for properties with constraints
                try:
                    if hasattr(prop, 'SubType'):
                        if prop.SubType == 2:  # Range
                            properties[prop_name]["range"] = {
                                "min": prop.SubTypeMin,
                                "max": prop.SubTypeMax,
                                "step": prop.SubTypeStep,
                            }
                        elif prop.SubType == 1:  # List
                            properties[prop_name]["valid_values"] = list(prop.SubTypeValues)
                except:
                    pass

            except Exception as e:
                properties[prop_name] = {
                    "id": prop.PropertyID,
                    "error": str(e),
                }

        return properties

    def get_item_properties(self, item_index: int = 1) -> Dict[str, Any]:
        """Get all properties for a scanner item (scan source)."""
        if self._device is None:
            raise RuntimeError("Not connected to scanner")

        properties = {}

        try:
            item = self._device.Items(item_index)
            props = item.Properties

            for i in range(1, props.Count + 1):
                prop = props.Item(i)
                prop_name = WIA_PROPERTY_NAMES.get(prop.PropertyID, f"Unknown_{prop.PropertyID}")

                try:
                    value = prop.Value

                    prop_info = {
                        "id": prop.PropertyID,
                        "value": value,
                        "type": prop.Type,
                        "is_readonly": prop.IsReadOnly if hasattr(prop, 'IsReadOnly') else None,
                    }

                    # Special decoding for known properties
                    if prop.PropertyID == 4103:  # Data Type
                        prop_info["decoded"] = DATA_TYPES.get(value, f"Unknown ({value})")
                    elif prop.PropertyID in (3074, 3075, 3076, 3088, 6159):
                        prop_info["decoded"] = decode_doc_handling(value) if isinstance(value, int) else None

                    # Get range/list constraints
                    try:
                        if hasattr(prop, 'SubType'):
                            if prop.SubType == 2:  # Range
                                prop_info["range"] = {
                                    "min": prop.SubTypeMin,
                                    "max": prop.SubTypeMax,
                                    "step": prop.SubTypeStep,
                                }
                            elif prop.SubType == 1:  # List
                                prop_info["valid_values"] = list(prop.SubTypeValues)
                    except:
                        pass

                    properties[prop_name] = prop_info

                except Exception as e:
                    properties[prop_name] = {
                        "id": prop.PropertyID,
                        "error": str(e),
                    }
        except Exception as e:
            return {"error": str(e)}

        return properties

    def get_all_items(self) -> List[Dict[str, Any]]:
        """Get properties for all scanner items."""
        if self._device is None:
            raise RuntimeError("Not connected to scanner")

        items = []
        count = self._device.Items.Count

        for i in range(1, count + 1):
            item_props = self.get_item_properties(i)
            items.append({
                "index": i,
                "properties": item_props,
            })

        return items

    def dump_all(self) -> Dict[str, Any]:
        """Dump all scanner information."""
        return {
            "device_properties": self.get_device_properties(),
            "items": self.get_all_items(),
        }

    def close(self):
        """Close the connection."""
        self._device = None


def run_diagnostic():
    """Run the diagnostic and print results."""
    print("=" * 70)
    print("Fujitsu Scanner WIA Diagnostic")
    print("=" * 70)
    print()

    diag = WIADiagnostic()

    # List scanners
    print("Scanning for devices...")
    scanners = diag.list_scanners()

    print(f"\nFound {len(scanners)} scanner(s):")
    for scanner in scanners:
        print(f"\n  Device ID: {scanner['device_id']}")
        for name, prop in scanner['properties'].items():
            print(f"    {name}: {prop['value']}")

    if not scanners:
        print("No scanners found!")
        return

    # Connect to scanner
    print("\n" + "-" * 70)
    print("Connecting to scanner...")
    diag.connect_scanner()
    print("Connected!")

    # Device properties
    print("\n" + "-" * 70)
    print("DEVICE PROPERTIES")
    print("-" * 70)

    device_props = diag.get_device_properties()
    for name, prop in sorted(device_props.items(), key=lambda x: x[1].get('id', 0)):
        if 'error' in prop:
            print(f"  [{prop['id']:5d}] {name}: ERROR - {prop['error']}")
        else:
            value_str = str(prop['value'])
            readonly = " [READ-ONLY]" if prop.get('is_readonly') else ""
            print(f"  [{prop['id']:5d}] {name}: {value_str}{readonly}")

            if 'decoded' in prop:
                print(f"          -> {prop['decoded']}")
            if 'range' in prop:
                r = prop['range']
                print(f"          Range: {r['min']} - {r['max']} (step: {r['step']})")
            if 'valid_values' in prop:
                print(f"          Valid: {prop['valid_values']}")

    # Item properties
    print("\n" + "-" * 70)
    print("SCANNER ITEM PROPERTIES (Scan Sources)")
    print("-" * 70)

    items = diag.get_all_items()
    for item in items:
        print(f"\nItem {item['index']}:")

        if 'error' in item['properties']:
            print(f"  ERROR: {item['properties']['error']}")
            continue

        # Group by category
        interesting_props = []
        other_props = []

        for name, prop in sorted(item['properties'].items(), key=lambda x: x[1].get('id', 0)):
            prop_id = prop.get('id', 0)
            # Properties related to feeding/document handling
            if prop_id in (3074, 3075, 3076, 3088, 3090, 3091, 3096, 6159, 6160, 6161, 6162, 6166, 6167, 6168, 6177, 6185, 6186, 6187):
                interesting_props.append((name, prop))
            else:
                other_props.append((name, prop))

        if interesting_props:
            print("\n  ** FEEDING/DOCUMENT HANDLING PROPERTIES **")
            for name, prop in interesting_props:
                _print_property(name, prop)

        print("\n  OTHER PROPERTIES:")
        for name, prop in other_props:
            _print_property(name, prop)

    diag.close()

    print("\n" + "=" * 70)
    print("Diagnostic complete!")
    print("=" * 70)


def _print_property(name: str, prop: Dict[str, Any]):
    """Helper to print a single property."""
    if 'error' in prop:
        print(f"    [{prop['id']:5d}] {name}: ERROR - {prop['error']}")
    else:
        value_str = str(prop['value'])
        readonly = " [READ-ONLY]" if prop.get('is_readonly') else ""
        print(f"    [{prop['id']:5d}] {name}: {value_str}{readonly}")

        if 'decoded' in prop:
            print(f"            -> {prop['decoded']}")
        if 'range' in prop:
            r = prop['range']
            print(f"            Range: {r['min']} - {r['max']} (step: {r['step']})")
        if 'valid_values' in prop:
            print(f"            Valid: {prop['valid_values']}")


def query_property_constraints(device, item_index: int = 1) -> Dict[str, Any]:
    """Query detailed constraints for writable properties."""
    import win32com.client

    constraints = {}

    try:
        item = device.Items(item_index)
        props = item.Properties

        for i in range(1, props.Count + 1):
            prop = props.Item(i)

            if prop.IsReadOnly:
                continue

            prop_name = WIA_PROPERTY_NAMES.get(prop.PropertyID, f"Unknown_{prop.PropertyID}")
            prop_info = {
                "id": prop.PropertyID,
                "name": prop_name,
                "current_value": prop.Value,
                "type": prop.Type,
            }

            # Try to get SubType info (range or list)
            try:
                subtype = prop.SubType
                if subtype == 1:  # List (WIA_PROP_LIST)
                    prop_info["constraint"] = "list"
                    try:
                        prop_info["valid_values"] = list(prop.SubTypeValues)
                    except:
                        pass
                elif subtype == 2:  # Range (WIA_PROP_RANGE)
                    prop_info["constraint"] = "range"
                    try:
                        prop_info["min"] = prop.SubTypeMin
                        prop_info["max"] = prop.SubTypeMax
                        prop_info["step"] = prop.SubTypeStep
                    except:
                        pass
                elif subtype == 3:  # Flag (WIA_PROP_FLAG)
                    prop_info["constraint"] = "flag"
                elif subtype == 0:  # None (WIA_PROP_NONE)
                    prop_info["constraint"] = "none"
                else:
                    prop_info["constraint"] = f"unknown ({subtype})"
            except Exception as e:
                prop_info["constraint_error"] = str(e)

            constraints[prop_name] = prop_info

    except Exception as e:
        return {"error": str(e)}

    return constraints


def run_detailed_diagnostic():
    """Run detailed diagnostic including property constraints."""
    print("=" * 70)
    print("Detailed Scanner Property Analysis")
    print("=" * 70)
    print()

    diag = WIADiagnostic()

    try:
        diag.connect_scanner()
    except Exception as e:
        print(f"ERROR: {e}")
        return

    print("Querying writable property constraints...")
    print()

    constraints = query_property_constraints(diag._device)

    if 'error' in constraints:
        print(f"ERROR: {constraints['error']}")
        return

    print("-" * 70)
    print("WRITABLE PROPERTIES WITH CONSTRAINTS")
    print("-" * 70)

    for name, info in sorted(constraints.items(), key=lambda x: x[1]['id']):
        print(f"\n[{info['id']:5d}] {name}")
        print(f"        Current: {info['current_value']}")
        print(f"        Type: {info['type']}")

        if 'constraint' in info:
            print(f"        Constraint: {info['constraint']}")

            if info['constraint'] == 'range':
                min_val = info.get('min', '?')
                max_val = info.get('max', '?')
                step = info.get('step', '?')
                print(f"        Range: {min_val} to {max_val} (step {step})")

            elif info['constraint'] == 'list':
                valid = info.get('valid_values', [])
                print(f"        Valid values: {valid}")

        if 'constraint_error' in info:
            print(f"        Constraint error: {info['constraint_error']}")

    diag.close()
    print()
    print("=" * 70)


if __name__ == "__main__":
    run_diagnostic()
