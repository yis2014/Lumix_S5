const MCapstone=require('@alexaltea/capstone-js');
MCapstone().then(cs=>{
  const d=new cs.Capstone(cs.ARCH_ARM,cs.MODE_THUMB);
  for (const hex of ['b40c','bc0c','bf00','b40cbc0c']) {
    const b=Buffer.from(hex,'hex');
    const r=d.disasm(b,0x1000);
    console.log(hex, '->', r.map(i=>i.mnemonic+' '+i.op_str).join(' | '));
  }
  // compare with known hardware bytes
  for (const hex of ['f0b5','70b5']) {
    const b=Buffer.from(hex,'hex');
    console.log(hex, '->', d.disasm(b,0x1000).map(i=>i.mnemonic+' '+i.op_str).join(' | '));
  }
});
