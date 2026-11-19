@echo off
setlocal
rem COMPILE ONLY: this script never launches s5_usb_descriptors.exe.
call "D:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 -winsdk=10.0.19041.0
if errorlevel 1 exit /b %errorlevel%
pushd "%~dp0"
if errorlevel 1 exit /b %errorlevel%
cl.exe /nologo /std:c++17 /EHsc /utf-8 /W4 /WX /DUNICODE /D_UNICODE /guard:cf s5_usb_descriptors.cpp /Fe:s5_usb_descriptors.exe /Fo:s5_usb_descriptors.obj /link setupapi.lib /DYNAMICBASE /NXCOMPAT /guard:cf
set "build_rc=%errorlevel%"
popd
exit /b %build_rc%
