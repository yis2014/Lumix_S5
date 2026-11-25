export function driverState(driver) {
  if (!driver) return { title: '正在检测驱动…', type: 'info' };
  if (!driver.supported) return { title: '驱动安装仅支持 Windows 10/11', type: 'info' };
  if (driver.error) return { title: '驱动检测失败，请重新检测', description: driver.error, type: 'warning' };
  if (driver.ok) return { title: '驱动正常', description: 'WinUSB 已绑定，服务接口 GUID 已注册。', type: 'success' };
  if (driver.normalPresent && !driver.present) return { title: '检测到普通模式 2382，请进入临时服务模式', description: '请先关机，右转轮调到 P 档、左转轮调到单拍，再同时按住回放（PLAY）+ AF ON 键开机进入临时服务模式（否则会一直识别成其他模式）。', type: 'warning' };
  if (!driver.present) return { title: '未检测到服务模式设备', description: '请将右转轮调到 P 档、左转轮调到单拍，关机后同时按住回放（PLAY）+ AF ON 键开机进入临时服务模式，再连接 USB 数据线（否则会一直识别成其他模式）。', type: 'info' };
  if (driver.driverDetectable === false) return { title: '已连接，驱动状态尚无法确认', description: '请重新检测，或在设备管理器中检查 WinUSB 与接口 GUID。', type: 'warning' };
  if (driver.winusb && driver.guidRegistered === null) return { title: '已绑定 WinUSB，接口 GUID 尚无法确认', description: '请重新检测，或在高级区域查看手动验证方法。', type: 'warning' };
  if (driver.winusb && driver.guidRegistered === false) return { title: '已连接但未安装驱动（接口 GUID 缺失）', description: '重新安装 LumixTool 驱动以注册服务接口 GUID。', type: 'warning' };
  if (driver.winusb) return { title: 'WinUSB 设备异常，请重新检测', description: `设备问题代码：${driver.problemCode ?? '未知'}。请检查设备管理器或重新连接 USB。`, type: 'warning' };
  return { title: '已连接但未安装驱动', description: `当前驱动：${driver.driver || '无'}。请为服务接口安装 WinUSB。`, type: 'warning' };
}

export const needsDriverSetup = driver => !!driver?.supported && driver.present === true && !driver.ok && !driver.error && driver.driverDetectable !== false && (!driver.winusb || driver.guidRegistered === false);
