// Only ID1 has a confirmed trigger. Keep the other names open for local labels.
export const catalog = Array.from({ length: 28 }, (_, index) => ({
  index,
  name: index === 1 ? '对焦提示音' : `未命名 #${index}`,
  note: index === 1 ? '已确认：半按快门合焦' : index === 20 ? '参考资料称快门音但实测不符' : '',
}));

export function soundName(index, labels = {}) {
  return labels[index] || catalog[index]?.name || `未命名 #${index}`;
}
