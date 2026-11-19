// Native Windows WPD baseline for the user's DC-S5. No firmware/settings writes.
// Baseline queries device properties and the driver's supported vendor operations.
#define NOMINMAX
#include <windows.h>
#include <PortableDeviceApi.h>
#include <PortableDeviceTypes.h>
#include <initguid.h>
#include <PortableDevice.h>
#include <WpdMtpExtensions.h>
#include <wrl/client.h>
#include <iostream>
#include <string>
#include <vector>
#include <algorithm>
#include <cwctype>
#include <iomanip>
#include <stdexcept>
#include <limits>
#include <propvarutil.h>
void read_config(IPortableDevice* dev,const wchar_t* output,bool photoStyle=false,bool description=false);
void snapshot_properties(IPortableDevice* dev);
using Microsoft::WRL::ComPtr;
void check(HRESULT hr,const char* where){
    std::cout<<where<<"_hr=0x"<<std::hex<<std::setw(8)<<std::setfill('0')<<(unsigned long)hr<<std::dec<<std::endl;
    if(FAILED(hr))throw std::runtime_error(where);
}
ComPtr<IPortableDeviceValues> vals(){ComPtr<IPortableDeviceValues> p;check(CoCreateInstance(__uuidof(PortableDeviceValues),nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&p)),"create_values");return p;}
ComPtr<IPortableDeviceValues> command(const PROPERTYKEY& k){auto p=vals();check(p->SetGuidValue(WPD_PROPERTY_COMMON_COMMAND_CATEGORY,k.fmtid),"set_category");check(p->SetUnsignedIntegerValue(WPD_PROPERTY_COMMON_COMMAND_ID,k.pid),"set_command_id");return p;}
ComPtr<IPortableDeviceValues> send(IPortableDevice* d,IPortableDeviceValues* p,const char* label){
    ComPtr<IPortableDeviceValues> r;check(d->SendCommand(0,p,&r),label);
    HRESULT status=E_UNEXPECTED;check(r->GetErrorValue(WPD_PROPERTY_COMMON_HRESULT,&status),"get_command_status");
    DWORD ptp=0;if(SUCCEEDED(r->GetUnsignedIntegerValue(WPD_PROPERTY_MTP_EXT_RESPONSE_CODE,&ptp)))std::cout<<label<<"_ptp_response=0x"<<std::hex<<ptp<<std::dec<<std::endl;
    check(status,"command_status");return r;
}
void stringprop(IPortableDeviceValues* p,const PROPERTYKEY& k,const char* label){
    LPWSTR s=nullptr;HRESULT hr=p->GetStringValue(k,&s);std::cout<<label<<"_hr=0x"<<std::hex<<(unsigned long)hr<<std::dec<<std::endl;
    if(SUCCEEDED(hr)){int n=WideCharToMultiByte(CP_UTF8,0,s,-1,nullptr,0,nullptr,nullptr);std::vector<char> b(n);WideCharToMultiByte(CP_UTF8,0,s,-1,b.data(),n,nullptr,nullptr);std::cout<<label<<"="<<b.data()<<std::endl;CoTaskMemFree(s);}
}
int wmain(int argc,wchar_t** argv){
    bool configRead=(argc==3 && std::wstring(argv[1])==L"--config-read");
    bool propertyRead=(argc==2 && std::wstring(argv[1])==L"--properties-baseline");
    bool photoStyleRead=(argc==3 && std::wstring(argv[1])==L"--photo-style-read");
    bool photoStyleDesc=(argc==3 && std::wstring(argv[1])==L"--photo-style-desc");
    bool vendorAccess=configRead || propertyRead || photoStyleRead || photoStyleDesc || (argc==2 && std::wstring(argv[1])==L"--vendor-baseline");
    if(argc!=1 && !vendorAccess){std::cerr<<"Allowed: baseline, --vendor-baseline, --properties-baseline, --config-read NEW_FILE, --photo-style-read NEW_FILE, --photo-style-desc NEW_FILE. No arbitrary opcodes."<<std::endl;return 2;}
    if((configRead || photoStyleRead || photoStyleDesc) && GetFileAttributesW(argv[2])!=INVALID_FILE_ATTRIBUTES){std::cerr<<"Refuse to overwrite output"<<std::endl;return 2;}
    HRESULT init=CoInitializeEx(nullptr,COINIT_MULTITHREADED);if(FAILED(init))return 3;
    int exitcode=0;
    try{
        ComPtr<IPortableDeviceManager> mgr;check(CoCreateInstance(__uuidof(PortableDeviceManager),nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&mgr)),"create_manager");
        check(mgr->RefreshDeviceList(),"refresh_devices");DWORD count=0;check(mgr->GetDevices(nullptr,&count),"device_count");std::vector<LPWSTR> ids(count,nullptr);if(count)check(mgr->GetDevices(ids.data(),&count),"get_devices");
        std::vector<std::wstring> targets;
        for(auto id:ids){if(!id)continue;std::wstring text=id;std::transform(text.begin(),text.end(),text.begin(),[](wchar_t c){return (wchar_t)towlower(c);});if(text.find(L"vid_04da&pid_2374")!=std::wstring::npos || text.find(L"vid_04da&pid_2382")!=std::wstring::npos)targets.emplace_back(id);CoTaskMemFree(id);}
        std::cout<<"target_count="<<targets.size()<<std::endl;if(targets.size()!=1)throw std::runtime_error("Require exactly one DC-S5 VID04DA PID2374 or PID2382; no other device will be opened");
        std::wstring selectedPath=targets[0];std::transform(selectedPath.begin(),selectedPath.end(),selectedPath.begin(),[](wchar_t c){return (wchar_t)towlower(c);});bool tether=(selectedPath.find(L"vid_04da&pid_2382")!=std::wstring::npos);std::cout<<"usb_vid=0x04da\nusb_pid="<<(tether?"0x2382":"0x2374")<<std::endl;
        auto client=vals();check(client->SetStringValue(WPD_CLIENT_NAME,L"S5 Readonly Evidence"),"client_name");check(client->SetUnsignedIntegerValue(WPD_CLIENT_MAJOR_VERSION,1),"client_version");check(client->SetUnsignedIntegerValue(WPD_CLIENT_DESIRED_ACCESS,vendorAccess ? (GENERIC_READ|GENERIC_WRITE) : GENERIC_READ),"client_access");check(client->SetUnsignedIntegerValue(WPD_CLIENT_SECURITY_QUALITY_OF_SERVICE,SECURITY_IMPERSONATION),"client_security");
        ComPtr<IPortableDevice> dev;check(CoCreateInstance(__uuidof(PortableDeviceFTM),nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&dev)),"create_device");check(dev->Open(targets[0].c_str(),client.Get()),"open_device");
        ComPtr<IPortableDeviceContent> content;check(dev->Content(&content),"get_content");ComPtr<IPortableDeviceProperties> properties;check(content->Properties(&properties),"get_properties");
        ComPtr<IPortableDeviceKeyCollection> keys;check(CoCreateInstance(__uuidof(PortableDeviceKeyCollection),nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&keys)),"create_keys");check(keys->Add(WPD_DEVICE_MANUFACTURER),"key_manufacturer");check(keys->Add(WPD_DEVICE_MODEL),"key_model");check(keys->Add(WPD_DEVICE_FIRMWARE_VERSION),"key_firmware");
        ComPtr<IPortableDeviceValues> info;check(properties->GetValues(WPD_DEVICE_OBJECT_ID,keys.Get(),&info),"read_device_info");stringprop(info.Get(),WPD_DEVICE_MANUFACTURER,"manufacturer");stringprop(info.Get(),WPD_DEVICE_MODEL,"model");stringprop(info.Get(),WPD_DEVICE_FIRMWARE_VERSION,"firmware");
        // This asks the Windows driver for advertised vendor opcodes; not a vendor opcode probe.
        try{
            auto req=command(WPD_COMMAND_MTP_EXT_GET_SUPPORTED_VENDOR_OPCODES);auto r=send(dev.Get(),req.Get(),"get_supported_vendor_opcodes");
            ComPtr<IPortableDevicePropVariantCollection> ops;check(r->GetIPortableDevicePropVariantCollectionValue(WPD_PROPERTY_MTP_EXT_VENDOR_OPERATION_CODES,&ops),"get_opcode_list");DWORD n=0;check(ops->GetCount(&n),"opcode_count");std::cout<<"vendor_opcode_count="<<n<<std::endl;
            for(DWORD i=0;i<n;++i){PROPVARIANT v;PropVariantInit(&v);check(ops->GetAt(i,&v),"opcode_item");if(v.vt==VT_UI4)std::cout<<"vendor_opcode=0x"<<std::hex<<v.ulVal<<std::dec<<std::endl;else std::cout<<"unexpected_opcode_variant="<<v.vt<<std::endl;PropVariantClear(&v);}
        }catch(const std::exception& e){std::cout<<"vendor_capability_query_incomplete="<<e.what()<<std::endl;}
        if(configRead || photoStyleRead || photoStyleDesc){
            if(photoStyleDesc && !tether)throw std::runtime_error("New description experiment is restricted to established Tether PID2382 mode");
            LPWSTR model=nullptr;check(info->GetStringValue(WPD_DEVICE_MODEL,&model),"validate_target_model");bool target=(std::wstring(model)==L"DC-S5");CoTaskMemFree(model);if(!target)throw std::runtime_error("Unexpected camera model; refusing vendor read");
            read_config(dev.Get(),argv[2],photoStyleRead,photoStyleDesc);
        }
        if(propertyRead)snapshot_properties(dev.Get());
        check(dev->Close(),"close_device");std::cout<<"baseline_complete=true"<<std::endl;
    }catch(const std::exception& e){std::cerr<<"ERROR="<<e.what()<<std::endl;exitcode=1;}
    CoUninitialize();return exitcode;
}

void read_config(IPortableDevice* dev,const wchar_t* output,bool photoStyle,bool description){
    // Three fixed getter requests only. No opcode/parameter sweep and no data OUT.
    const DWORD opcode=description?0x9108:(photoStyle?0x9402:0x9421),tag=(photoStyle||description)?0x02000010:0x080000a2;
    std::cout<<"read_purpose="<<(description?"PhotoStyle_description":(photoStyle?"PhotoStyle_property":"configuration_export"))<<"\nconfig_opcode=0x"<<std::hex<<opcode<<std::dec<<"\nconfig_param_count="<<(description?3:1)<<"\nconfig_param0=0x"<<std::hex<<tag<<std::dec<<"\n";
    if(description)std::cout<<"config_param1=0x0\nconfig_param2=0x0\n";
    std::cout<<"data_direction=device_to_host\n"<<std::flush;
    auto request=command(WPD_COMMAND_MTP_EXT_EXECUTE_COMMAND_WITH_DATA_TO_READ);
    check(request->SetUnsignedIntegerValue(WPD_PROPERTY_MTP_EXT_OPERATION_CODE,opcode),"set_config_opcode");
    ComPtr<IPortableDevicePropVariantCollection> params;check(CoCreateInstance(__uuidof(PortableDevicePropVariantCollection),nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&params)),"create_config_params");
    PROPVARIANT p;PropVariantInit(&p);p.vt=VT_UI4;p.ulVal=tag;check(params->Add(&p),"add_config_tag");
    if(description){p.ulVal=0;check(params->Add(&p),"add_description_param1");check(params->Add(&p),"add_description_param2");}
    check(request->SetIPortableDevicePropVariantCollectionValue(WPD_PROPERTY_MTP_EXT_OPERATION_PARAMS,params.Get()),"set_config_params");
    auto begin=send(dev,request.Get(),"begin_config_read");
    DWORD earlyCode=0;if(SUCCEEDED(begin->GetUnsignedIntegerValue(WPD_PROPERTY_MTP_EXT_RESPONSE_CODE,&earlyCode)))std::cout<<"begin_ptp_response=0x"<<std::hex<<earlyCode<<std::dec<<std::endl;
    ULONGLONG total=0;check(begin->GetUnsignedLargeIntegerValue(WPD_PROPERTY_MTP_EXT_TRANSFER_TOTAL_DATA_SIZE,&total),"get_config_size");std::cout<<"config_reported_size="<<total<<std::endl;
    LPWSTR context=nullptr;check(begin->GetStringValue(WPD_PROPERTY_MTP_EXT_TRANSFER_CONTEXT,&context),"get_read_context");
    struct ContextOwner{LPWSTR p;~ContextOwner(){CoTaskMemFree(p);}}contextOwner{context};
    bool unknown=(total==0xffffffffULL || total==std::numeric_limits<ULONGLONG>::max());
    constexpr DWORD cap=1024*1024,chunk=64*1024;
    if(!unknown && total>cap)throw std::runtime_error("Refuse config transfer above 1MiB cap");
    std::vector<BYTE> all;all.reserve(unknown?chunk:(size_t)total);
    while(unknown || all.size()<total){
        if(all.size()>=cap)throw std::runtime_error("Config exceeded cap");
        DWORD wanted=unknown ? (DWORD)std::min<size_t>(chunk,cap-all.size()) : (DWORD)std::min<ULONGLONG>(chunk,total-all.size());
        auto req=command(WPD_COMMAND_MTP_EXT_READ_DATA);check(req->SetStringValue(WPD_PROPERTY_MTP_EXT_TRANSFER_CONTEXT,context),"read_set_context");check(req->SetUnsignedIntegerValue(WPD_PROPERTY_MTP_EXT_TRANSFER_NUM_BYTES_TO_READ,wanted),"read_set_size");
        std::vector<BYTE> buffer(wanted);check(req->SetBufferValue(WPD_PROPERTY_MTP_EXT_TRANSFER_DATA,buffer.data(),wanted),"read_set_buffer");auto r=send(dev,req.Get(),"read_config_chunk");
        DWORD got=0;check(r->GetUnsignedIntegerValue(WPD_PROPERTY_MTP_EXT_TRANSFER_NUM_BYTES_READ,&got),"read_get_count");BYTE* data=nullptr;DWORD bytes=0;check(r->GetBufferValue(WPD_PROPERTY_MTP_EXT_TRANSFER_DATA,&data,&bytes),"read_get_buffer");
        struct BufferOwner{BYTE* p;~BufferOwner(){CoTaskMemFree(p);}}bufferOwner{data};
        if(got>wanted || got>bytes || (got && !data))throw std::runtime_error("Invalid read lengths");
        if(got)all.insert(all.end(),data,data+got);std::cout<<"config_received="<<all.size()<<std::endl;
        if(!got){if(!unknown && all.size()!=total)throw std::runtime_error("Unexpected end of config stream");break;}
        if(unknown && got<wanted)break;
    }
    auto end=command(WPD_COMMAND_MTP_EXT_END_DATA_TRANSFER);check(end->SetStringValue(WPD_PROPERTY_MTP_EXT_TRANSFER_CONTEXT,context),"end_set_context");auto response=send(dev,end.Get(),"end_config_transfer");DWORD code=0;check(response->GetUnsignedIntegerValue(WPD_PROPERTY_MTP_EXT_RESPONSE_CODE,&code),"get_config_ptp_response");std::cout<<"config_ptp_response=0x"<<std::hex<<code<<std::dec<<std::endl;
    if(code!=0x2001)throw std::runtime_error("Configuration read did not return PTP OK");
    if(!unknown && all.size()!=total)throw std::runtime_error("Configuration length mismatch");
    HANDLE file=CreateFileW(output,GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);if(file==INVALID_HANDLE_VALUE)throw std::runtime_error("Cannot create new local output");DWORD written=0;BOOL ok=WriteFile(file,all.data(),(DWORD)all.size(),&written,nullptr);CloseHandle(file);if(!ok || written!=all.size())throw std::runtime_error("Incomplete local write");std::cout<<"config_saved_bytes="<<written<<std::endl;
}

std::string utf8(const wchar_t* value){if(!value)return {};int n=WideCharToMultiByte(CP_UTF8,0,value,-1,nullptr,0,nullptr,nullptr);if(n<=0)return {};std::vector<char> b(n);WideCharToMultiByte(CP_UTF8,0,value,-1,b.data(),n,nullptr,nullptr);return std::string(b.data());}
std::string jsonquote(const std::string& value){std::string r="\"";const char* h="0123456789abcdef";for(unsigned char c:value){if(c=='"'||c=='\\'){r+='\\';r+=(char)c;}else if(c<32){r+="\\u00";r+=h[c>>4];r+=h[c&15];}else r+=(char)c;}return r+"\"";}
void snapshot_properties(IPortableDevice* dev){
    ComPtr<IPortableDeviceContent> content;check(dev->Content(&content),"snapshot_content");
    ComPtr<IPortableDeviceProperties> properties;check(content->Properties(&properties),"snapshot_properties");
    ComPtr<IPortableDeviceKeyCollection> keys;check(properties->GetSupportedProperties(WPD_DEVICE_OBJECT_ID,&keys),"snapshot_supported_keys");
    DWORD n=0;check(keys->GetCount(&n),"snapshot_key_count");std::cout<<"device_supported_property_count="<<n<<std::endl;if(n>4096)throw std::runtime_error("Unexpectedly many properties");
    ComPtr<IPortableDeviceValues> values;check(properties->GetValues(WPD_DEVICE_OBJECT_ID,keys.Get(),&values),"snapshot_get_values");check(values->GetCount(&n),"snapshot_value_count");
    for(DWORD i=0;i<n;++i){PROPERTYKEY key={};PROPVARIANT value;PropVariantInit(&value);check(values->GetAt(i,&key,&value),"snapshot_get_value");wchar_t guid[40]={};StringFromGUID2(key.fmtid,guid,40);LPWSTR text=nullptr;HRESULT hr=PropVariantToStringAlloc(value,&text);
        std::cout<<"PROP_JSON={\"fmtid\":"<<jsonquote(utf8(guid))<<",\"pid\":"<<key.pid<<",\"vt\":"<<value.vt<<",\"conversion_hr\":"<<(unsigned long)hr<<",\"value\":"<<jsonquote(SUCCEEDED(hr)?utf8(text):std::string("<not a scalar string>"))<<"}"<<std::endl;
        CoTaskMemFree(text);PropVariantClear(&value);
    }
}
