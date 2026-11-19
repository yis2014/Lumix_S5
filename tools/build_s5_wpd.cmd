@echo off
call "D:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64
if errorlevel 1 exit /b %errorlevel%
cl.exe /nologo /std:c++17 /EHsc /utf-8 /W4 s5_wpd_readonly.cpp /Fe:s5_wpd_readonly.exe /link ole32.lib propsys.lib PortableDeviceGuids.lib
exit /b %errorlevel%
