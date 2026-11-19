// Read-only Windows USB HUB descriptor inspection for DC-S5 VID 04DA PID 2374/2382.
// NEVER opens a camera/bulk/WPD interface. NEVER sends PTP, control OUT,
// SET_CONFIGURATION, reset, cycle-port, driver installation or rebinding.
// GENERIC_WRITE on a HUB handle is required by the Windows HUB descriptor IOCTL
// API; it is an access right, NOT a USB device write. Only three allowlisted
// query IOCTLs occur in this file. GET_DESCRIPTOR is always IN (0x80), request 6.
// No string descriptors are requested, including iSerialNumber. No other device
// identity, hub interface paths, device address or serial number is printed.
// Compile only via build_s5_usb_descriptors.cmd; execution requires separate review.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define _WIN32_WINNT 0x0601
#include <windows.h>
#include <winioctl.h>
#include <setupapi.h>
#include <usb.h>
#include <usbioctl.h>
#include <usbiodef.h>
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <new>
#include <set>
#include <string>
#include <utility>
#include <vector>
#include <initguid.h>
// Define only this GUID locally; do not depend on a device-specific driver SDK.
DEFINE_GUID(kUsbHubInterface, 0xf18a0e88, 0xc30c, 0x11d0,
            0x88, 0x15, 0x00, 0xa0, 0xc9, 0x06, 0xbe, 0xd8);

namespace {
constexpr size_t kMaxConfigurations = 8;
constexpr size_t kMaxDescriptorBytes = 65535;
constexpr size_t kMaxHubPathBytes = 1024 * 1024;
constexpr size_t kConnectionBytes = sizeof(USB_NODE_CONNECTION_INFORMATION_EX)
                                    + 32 * sizeof(USB_PIPE_INFO);
struct Handle {
    HANDLE value = INVALID_HANDLE_VALUE;
    explicit Handle(HANDLE h = INVALID_HANDLE_VALUE) : value(h) {}
    ~Handle() { if (value != INVALID_HANDLE_VALUE) CloseHandle(value); }
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
    Handle(Handle&& h) noexcept : value(h.value) { h.value = INVALID_HANDLE_VALUE; }
    Handle& operator=(Handle&& h) noexcept {
        if (this != &h) {
            if (value != INVALID_HANDLE_VALUE) CloseHandle(value);
            value = h.value; h.value = INVALID_HANDLE_VALUE;
        }
        return *this;
    }
};
struct DeviceSet {
    HDEVINFO value;
    ~DeviceSet() { if (value != INVALID_HANDLE_VALUE) SetupDiDestroyDeviceInfoList(value); }
};
// Own fixed-size snapshot avoids constructing the SDK's flexible PipeList[0]
// structure as a standalone C++ object (MSVC diagnoses that under /W4 /WX).
struct ConnectionSnapshot {
    USB_DEVICE_DESCRIPTOR DeviceDescriptor{};
    UCHAR CurrentConfigurationValue = 0;
    BOOLEAN DeviceIsHub = FALSE;
    USHORT DeviceAddress = 0;
    USB_CONNECTION_STATUS ConnectionStatus = NoDeviceConnected;
};
struct Candidate {
    size_t hub;
    ULONG port;
    ConnectionSnapshot initial;
};
void Error(const char* stage, DWORD code, size_t hub, ULONG port,
           const char* reason = "windows_api_failure") {
    std::cout << "{\"event\":\"error\",\"stage\":\"" << stage
              << "\",\"win32_error\":" << code << ",\"hub_ordinal\":" << hub
              << ",\"port\":" << port << ",\"reason\":\"" << reason
              << "\",\"access_denied\":" << (code == ERROR_ACCESS_DENIED ? "true" : "false")
              << "}\n";
}
bool Bounds(const char* stage, size_t hub, ULONG port, const char* reason) {
    Error(stage, ERROR_INVALID_DATA, hub, port, reason); return false;
}
unsigned U16(const unsigned char* p) { return p[0] | (unsigned(p[1]) << 8); }
std::string Hex(const std::vector<unsigned char>& bytes) {
    constexpr char digits[] = "0123456789abcdef";
    std::string s; s.reserve(bytes.size() * 2);
    for (unsigned char b : bytes) { s += digits[b >> 4]; s += digits[b & 15]; }
    return s;
}
bool Target(const ConnectionSnapshot& c) {
    return c.ConnectionStatus == DeviceConnected && !c.DeviceIsHub &&
           c.DeviceDescriptor.idVendor == 0x04da &&
           (c.DeviceDescriptor.idProduct == 0x2374 || c.DeviceDescriptor.idProduct == 0x2382);
}
bool Connection(HANDLE hubHandle, size_t hub, ULONG port,
                ConnectionSnapshot& out) {
    // Pipe list is bounded by 32 USB endpoint addresses; never parse the pipe list.
    alignas(USB_NODE_CONNECTION_INFORMATION_EX) std::array<unsigned char, kConnectionBytes> buf{};
    auto* query = reinterpret_cast<USB_NODE_CONNECTION_INFORMATION_EX*>(buf.data());
    query->ConnectionIndex = port;
    DWORD returned = 0;
    if (!DeviceIoControl(hubHandle, IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX,
                         buf.data(), static_cast<DWORD>(buf.size()),
                         buf.data(), static_cast<DWORD>(buf.size()), &returned, nullptr)) {
        Error("connection_query", GetLastError(), hub, port); return false;
    }
    if (returned < sizeof(USB_NODE_CONNECTION_INFORMATION_EX) || returned > buf.size())
        return Bounds("connection_query", hub, port, "invalid_returned_size");
    if (query->ConnectionIndex != port) {
        // SDK marks ConnectionIndex INPUT, not an echo-output contract. Permit
        // only a canonical fully empty output port to clear that input field.
        // Connected/failed/partial ports still fail closed; identity checks unchanged.
        const auto* descriptorBytes = reinterpret_cast<const unsigned char*>(&query->DeviceDescriptor);
        const bool descriptorAllZero = std::all_of(
            descriptorBytes, descriptorBytes + sizeof(USB_DEVICE_DESCRIPTOR),
            [](unsigned char byte) { return byte == 0; });
        const bool canonicalEmptyPort = query->ConnectionIndex == 0 &&
            query->ConnectionStatus == NoDeviceConnected && descriptorAllZero &&
            !query->DeviceIsHub && query->DeviceAddress == 0 &&
            query->NumberOfOpenPipes == 0 && query->CurrentConfigurationValue == 0;
        std::cout << "{\"event\":\"connection_index_mismatch_diagnostic\",\"hub_ordinal\":" << hub
                  << ",\"requested_connection_index\":" << port
                  << ",\"returned_connection_index\":" << query->ConnectionIndex
                  << ",\"connection_status\":" << static_cast<unsigned>(query->ConnectionStatus)
                  << ",\"returned_bytes\":" << returned
                  << ",\"minimum_header_bytes\":" << sizeof(USB_NODE_CONNECTION_INFORMATION_EX)
                  << ",\"cached_device_descriptor_all_zero\":" << (descriptorAllZero ? "true" : "false")
                  << ",\"legacy_index_echo_check_passed\":false}\n";
        if (!canonicalEmptyPort) return Bounds("connection_query", hub, port, "port_index_mismatch");
        std::cout << "{\"event\":\"canonical_empty_port_input_field_cleared\",\"hub_ordinal\":" << hub
                  << ",\"port\":" << port << ",\"validated_empty_port\":true,\"descriptor_all_zero\":true,\"address_zero\":true,\"pipes_zero\":true,\"configuration_zero\":true,\"not_a_hub\":true}\n";
    }
    out.DeviceDescriptor = query->DeviceDescriptor;
    out.CurrentConfigurationValue = query->CurrentConfigurationValue;
    out.DeviceIsHub = query->DeviceIsHub;
    out.DeviceAddress = query->DeviceAddress;
    out.ConnectionStatus = query->ConnectionStatus;
    return true;
}
bool Revalidate(HANDLE h, const Candidate& c) {
    ConnectionSnapshot now;
    if (!Connection(h, c.hub, c.port, now)) return false;
    if (!Target(now) || now.DeviceAddress != c.initial.DeviceAddress ||
        std::memcmp(&now.DeviceDescriptor, &c.initial.DeviceDescriptor,
                    sizeof(USB_DEVICE_DESCRIPTOR)) != 0 ||
        now.CurrentConfigurationValue != c.initial.CurrentConfigurationValue)
        return Bounds("revalidate", c.hub, c.port, "connection_changed_abort_no_retry");
    return true;
}
bool GetConfiguration(HANDLE h, const Candidate& c, unsigned index, USHORT length,
                      std::vector<unsigned char>& data) {
    if (index >= kMaxConfigurations || length < 9 || length > kMaxDescriptorBytes)
        return Bounds("get_descriptor", c.hub, c.port, "request_bounds");
    if (!Revalidate(h, c)) return false;
    // There is deliberately no generic request/type parameter: CONFIGURATION only.
    const size_t header = offsetof(USB_DESCRIPTOR_REQUEST, Data);
    std::vector<unsigned char> buf(header + length, 0);
    auto* req = reinterpret_cast<USB_DESCRIPTOR_REQUEST*>(buf.data());
    req->ConnectionIndex = c.port;
    req->SetupPacket.bmRequest = 0x80; // device-to-host, standard, device
    req->SetupPacket.bRequest = 6;     // GET_DESCRIPTOR only
    req->SetupPacket.wValue = static_cast<USHORT>((USB_CONFIGURATION_DESCRIPTOR_TYPE << 8) | index);
    req->SetupPacket.wIndex = 0;
    req->SetupPacket.wLength = length;
    DWORD returned = 0;
    if (!DeviceIoControl(h, IOCTL_USB_GET_DESCRIPTOR_FROM_NODE_CONNECTION,
                         buf.data(), static_cast<DWORD>(buf.size()),
                         buf.data(), static_cast<DWORD>(buf.size()), &returned, nullptr)) {
        Error("get_configuration_descriptor", GetLastError(), c.hub, c.port); return false;
    }
    if (returned < header || returned > buf.size())
        return Bounds("get_descriptor", c.hub, c.port, "invalid_returned_size");
    data.assign(buf.begin() + header, buf.begin() + returned);
    // Always log the actual returned raw configuration bytes, even on a short reply.
    std::cout << "{\"event\":\"raw_configuration\",\"configuration_index\":" << index
              << ",\"requested_bytes\":" << length << ",\"returned_bytes\":" << data.size()
              << ",\"hex\":\"" << Hex(data) << "\"}\n";
    if (!Revalidate(h, c)) return false;
    if (data.size() != length)
        return Bounds("get_descriptor", c.hub, c.port, "short_descriptor_reply");
    return true;
}
bool ParseConfiguration(const std::vector<unsigned char>& d, unsigned index,
                        const Candidate& c) {
    auto bad = [&](const char* reason) { return Bounds("parse_configuration", c.hub, c.port, reason); };
    if (d.size() < 9 || d[0] != 9 || d[1] != USB_CONFIGURATION_DESCRIPTOR_TYPE ||
        U16(d.data() + 2) != d.size()) return bad("invalid_configuration_header_or_wTotalLength");
    std::cout << "{\"event\":\"configuration\",\"configuration_index\":" << index
              << ",\"wTotalLength\":" << d.size() << ",\"bConfigurationValue\":" << unsigned(d[5])
              << ",\"bNumInterfaces\":" << unsigned(d[4]) << ",\"bmAttributes\":" << unsigned(d[7])
              << ",\"bMaxPower_raw\":" << unsigned(d[8]) << "}\n";
    int interfaceNumber = -1, alternate = -1, expectedEndpoints = 0, endpoints = 0;
    std::set<unsigned> interfaceNumbers;
    std::set<std::pair<unsigned, unsigned>> alternates;
    std::set<unsigned> endpointAddresses;
    for (size_t pos = 0; pos < d.size();) {
        if (d.size() - pos < 2) return bad("truncated_descriptor_header");
        const unsigned length = d[pos], type = d[pos + 1];
        if (length < 2 || length > d.size() - pos) return bad("invalid_bLength_or_overrun");
        const unsigned char* p = d.data() + pos;
        std::cout << "{\"event\":\"descriptor\",\"configuration_index\":" << index
                  << ",\"offset\":" << pos << ",\"bLength\":" << length
                  << ",\"bDescriptorType\":" << type << "}\n";
        if (type == USB_CONFIGURATION_DESCRIPTOR_TYPE && pos != 0)
            return bad("nested_configuration_descriptor");
        if (type == USB_INTERFACE_DESCRIPTOR_TYPE) {
            if (length < 9) return bad("short_interface_descriptor");
            if (interfaceNumber >= 0 && endpoints != expectedEndpoints) return bad("endpoint_count_mismatch");
            interfaceNumber = p[2]; alternate = p[3]; expectedEndpoints = p[4]; endpoints = 0;
            endpointAddresses.clear();
            interfaceNumbers.insert(p[2]);
            if (!alternates.emplace(p[2], p[3]).second) return bad("duplicate_interface_alternate");
            std::cout << "{\"event\":\"interface\",\"configuration_index\":" << index
                      << ",\"offset\":" << pos << ",\"interface\":" << interfaceNumber
                      << ",\"alternate\":" << alternate << ",\"bNumEndpoints\":" << expectedEndpoints
                      << ",\"class\":" << unsigned(p[5]) << ",\"subclass\":" << unsigned(p[6])
                      << ",\"protocol\":" << unsigned(p[7]) << "}\n";
        } else if (type == USB_ENDPOINT_DESCRIPTOR_TYPE) {
            if (length < 7 || interfaceNumber < 0) return bad("short_or_orphan_endpoint");
            if ((p[2] & 15) == 0 || (p[2] & 0x70) != 0 ||
                !endpointAddresses.insert(p[2]).second) return bad("invalid_or_duplicate_endpoint_address");
            ++endpoints;
            constexpr const char* transfer[] = {"control", "isochronous", "bulk", "interrupt"};
            const unsigned maxpacket = U16(p + 4);
            std::cout << "{\"event\":\"endpoint\",\"configuration_index\":" << index
                      << ",\"offset\":" << pos << ",\"interface\":" << interfaceNumber
                      << ",\"alternate\":" << alternate << ",\"address\":" << unsigned(p[2])
                      << ",\"direction\":\"" << ((p[2] & 0x80) ? "IN" : "OUT")
                      << "\",\"type\":\"" << transfer[p[3] & 3]
                      << "\",\"bmAttributes\":" << unsigned(p[3])
                      << ",\"maxpacket\":" << maxpacket << ",\"maxpacket_payload\":" << (maxpacket & 0x7ff)
                      << ",\"interval\":" << unsigned(p[6]) << "}\n";
        }
        pos += length; // progress is guaranteed by bLength >= 2 and the remaining-size check
    }
    if (interfaceNumber >= 0 && endpoints != expectedEndpoints) return bad("endpoint_count_mismatch");
    if (interfaceNumbers.size() != d[4]) return bad("interface_count_mismatch");
    for (unsigned number : interfaceNumbers)
        if (alternates.count({number, 0}) == 0) return bad("missing_default_alternate");
    std::cout << "{\"event\":\"configuration_validated\",\"configuration_index\":" << index << "}\n";
    return true;
}
int Run() {
    std::cout << "{\"event\":\"policy\",\"version\":1,\"hub_query_only\":true,"
                 "\"strings_requested\":false,\"serial_requested\":false,"
                 "\"max_configurations\":8,\"max_configuration_bytes\":65535,"
                 "\"generic_write_is_hub_api_access_not_device_write\":true}\n";
    DeviceSet devices{SetupDiGetClassDevsW(&kUsbHubInterface, nullptr, nullptr,
                                          DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)};
    if (devices.value == INVALID_HANDLE_VALUE) {
        Error("SetupDiGetClassDevs", GetLastError(), 0, 0); return 2;
    }
    bool complete = true;
    std::vector<Handle> hubs;
    std::vector<Candidate> candidates;
    for (DWORD ordinal = 0;; ++ordinal) {
        SP_DEVICE_INTERFACE_DATA iface{}; iface.cbSize = sizeof(iface);
        if (!SetupDiEnumDeviceInterfaces(devices.value, nullptr, &kUsbHubInterface, ordinal, &iface)) {
            const DWORD error = GetLastError();
            if (error != ERROR_NO_MORE_ITEMS) { Error("SetupDiEnumDeviceInterfaces", error, ordinal, 0); complete = false; }
            break;
        }
        DWORD needed = 0;
        const BOOL probe = SetupDiGetDeviceInterfaceDetailW(devices.value, &iface, nullptr, 0, &needed, nullptr);
        const DWORD probeError = probe ? ERROR_SUCCESS : GetLastError();
        if (probe || probeError != ERROR_INSUFFICIENT_BUFFER ||
            needed < sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_W) || needed > kMaxHubPathBytes) {
            Error("SetupDi_detail_size", probeError, ordinal, 0, "invalid_path_size_query"); complete = false; continue;
        }
        std::vector<unsigned char> detailBuffer(needed, 0);
        auto* detail = reinterpret_cast<SP_DEVICE_INTERFACE_DETAIL_DATA_W*>(detailBuffer.data());
        detail->cbSize = sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_W);
        if (!SetupDiGetDeviceInterfaceDetailW(devices.value, &iface, detail, needed, nullptr, nullptr)) {
            Error("SetupDi_detail", GetLastError(), ordinal, 0); complete = false; continue;
        }
        const size_t pathCharacters = (needed - offsetof(SP_DEVICE_INTERFACE_DETAIL_DATA_W, DevicePath)) / sizeof(WCHAR);
        if (std::find(detail->DevicePath, detail->DevicePath + pathCharacters, L'\0') == detail->DevicePath + pathCharacters) {
            Bounds("hub_path", ordinal, 0, "missing_path_terminator"); complete = false; continue;
        }
        Handle handle(CreateFileW(detail->DevicePath, GENERIC_WRITE,
                                  FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr,
                                  OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr));
        if (handle.value == INVALID_HANDLE_VALUE) {
            // Fail closed. No elevation, alternate access mode, rebinding or retry.
            Error("open_hub", GetLastError(), ordinal, 0); complete = false; continue;
        }
        USB_NODE_INFORMATION node{}; node.NodeType = UsbHub;
        DWORD returned = 0;
        if (!DeviceIoControl(handle.value, IOCTL_USB_GET_NODE_INFORMATION,
                             &node, sizeof(node), &node, sizeof(node), &returned, nullptr)) {
            Error("hub_node_information", GetLastError(), ordinal, 0); complete = false; continue;
        }
        if (returned < sizeof(node) || returned > sizeof(node) || node.NodeType != UsbHub ||
            node.u.HubInformation.HubDescriptor.bNumberOfPorts == 0) {
            Bounds("hub_node_information", ordinal, 0, "invalid_hub_information"); complete = false; continue;
        }
        const ULONG ports = node.u.HubInformation.HubDescriptor.bNumberOfPorts; // UCHAR: <= 255
        const size_t hubIndex = hubs.size();
        hubs.push_back(std::move(handle));
        for (ULONG port = 1; port <= ports; ++port) {
            ConnectionSnapshot info;
            if (!Connection(hubs[hubIndex].value, hubIndex, port, info)) { complete = false; continue; }
            if (info.ConnectionStatus != NoDeviceConnected && info.ConnectionStatus != DeviceConnected) {
                Bounds("connection_query", hubIndex, port, "unresolved_connection_status");
                complete = false; continue;
            }
            if (info.ConnectionStatus == DeviceConnected &&
                (info.DeviceDescriptor.bLength != sizeof(USB_DEVICE_DESCRIPTOR) ||
                 info.DeviceDescriptor.bDescriptorType != USB_DEVICE_DESCRIPTOR_TYPE)) {
                Bounds("connection_query", hubIndex, port, "invalid_cached_device_descriptor");
                complete = false; continue;
            }
            if (Target(info)) candidates.push_back({hubIndex, port, info});
            // No logging of any non-target device descriptor or identity.
        }
    }
    std::cout << "{\"event\":\"candidate_summary\",\"count\":" << candidates.size()
              << ",\"enumeration_complete\":" << (complete ? "true" : "false") << "}\n";
    if (!complete || candidates.size() != 1) {
        std::cout << "{\"event\":\"refused\",\"reason\":\"requires_complete_enumeration_and_exactly_one_target\"}\n";
        return 3;
    }
    const Candidate& c = candidates.front();
    const auto& dd = c.initial.DeviceDescriptor;
    if (dd.bLength != sizeof(USB_DEVICE_DESCRIPTOR) || dd.bDescriptorType != USB_DEVICE_DESCRIPTOR_TYPE ||
        dd.bNumConfigurations == 0 || dd.bNumConfigurations > kMaxConfigurations) {
        Bounds("target_device_descriptor", c.hub, c.port, "invalid_device_descriptor_or_configuration_count"); return 4;
    }
    std::cout << "{\"event\":\"target\",\"vid\":\"04da\",\"pid\":\""
              << (dd.idProduct == 0x2374 ? "2374" : "2382") << "\",\"configuration_count\":"
              << unsigned(dd.bNumConfigurations) << ",\"hub_ordinal\":" << c.hub << ",\"port\":" << c.port << "}\n";
    const auto* deviceBytes = reinterpret_cast<const unsigned char*>(&dd);
    std::vector<unsigned char> rawDevice(deviceBytes, deviceBytes + sizeof(dd));
    std::cout << "{\"event\":\"device_descriptor\",\"source\":\"hub_cached_connection_info\",\"hex\":\"" << Hex(rawDevice)
              << "\",\"bcdUSB\":" << dd.bcdUSB << ",\"device_class\":" << unsigned(dd.bDeviceClass)
              << ",\"device_subclass\":" << unsigned(dd.bDeviceSubClass) << ",\"device_protocol\":" << unsigned(dd.bDeviceProtocol)
              << ",\"maxpacket0\":" << unsigned(dd.bMaxPacketSize0) << ",\"bcdDevice\":" << dd.bcdDevice
              << ",\"current_configuration_value\":" << unsigned(c.initial.CurrentConfigurationValue) << "}\n";
    std::set<unsigned> configurationValues;
    for (unsigned index = 0; index < dd.bNumConfigurations; ++index) {
        std::vector<unsigned char> header, full;
        HANDLE h = hubs[c.hub].value;
        if (!GetConfiguration(h, c, index, 9, header)) return 4;
        if (header[0] != 9 || header[1] != USB_CONFIGURATION_DESCRIPTOR_TYPE || U16(header.data() + 2) < 9) {
            Bounds("configuration_header", c.hub, c.port, "invalid_header_or_wTotalLength"); return 4;
        }
        const auto total = static_cast<USHORT>(U16(header.data() + 2));
        if (!GetConfiguration(h, c, index, total, full)) return 4;
        if (!std::equal(header.begin(), header.end(), full.begin())) {
            Bounds("configuration_header", c.hub, c.port, "header_changed_between_reads"); return 4;
        }
        if (!ParseConfiguration(full, index, c)) return 4;
        if (full[5] == 0 || !configurationValues.insert(full[5]).second) {
            Bounds("configuration_value", c.hub, c.port, "zero_or_duplicate_configuration_value"); return 4;
        }
    }
    std::cout << "{\"event\":\"done\",\"ok\":true,\"configurations_read\":"
              << unsigned(dd.bNumConfigurations) << "}\n";
    return 0;
}
} // namespace
int main(int argc, char**) {
    // No command line can enable another protocol, interface, IOCTL or target.
    if (argc != 1) {
        std::cout << "{\"event\":\"refused\",\"reason\":\"no_arguments_supported\"}\n";
        return 1;
    }
    try { return Run(); }
    catch (const std::bad_alloc&) {
        std::cout << "{\"event\":\"error\",\"reason\":\"allocation_failure\"}\n"; return 5;
    }
    catch (...) {
        std::cout << "{\"event\":\"error\",\"reason\":\"unexpected_cpp_exception\"}\n"; return 5;
    }
}
