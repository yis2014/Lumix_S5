import { useEffect, useRef } from 'react';
import { Flex, Typography, theme } from 'antd';

export default function Waveform({ buffer, active }) {
  const canvasRef = useRef(null);
  const { token } = theme.useToken();
  useEffect(() => {
    if (!active || !buffer) return;
    const canvas = canvasRef.current;
    function draw() {
      const width = canvas.clientWidth;
      if (!width) return;
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(100 * ratio);
      const drawing = canvas.getContext('2d');
      drawing.scale(ratio, ratio);
      const channel = buffer.getChannelData(0);
      const bars = Math.max(20, Math.floor(width / 4));
      drawing.fillStyle = token.colorPrimary;
      for (let index = 0; index < bars; index++) {
        const start = Math.floor(index * channel.length / bars);
        const end = Math.min(channel.length, Math.max(start + 1, Math.floor((index + 1) * channel.length / bars)));
        let peak = 0;
        for (let sample = start; sample < end; sample++) peak = Math.max(peak, Math.abs(channel[sample]));
        const height = Math.max(2, peak * 84);
        drawing.fillRect(index * width / bars, 50 - height / 2, 2, height);
      }
    }
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    draw();
    return () => observer.disconnect();
  }, [buffer, active, token.colorPrimary]);

  return <div className="waveform-panel" style={{ background: token.colorFillAlter }}>
    <canvas id="waveform" ref={canvasRef} className="waveform" role="img" aria-label="将写入相机的音频波形" />
    <Flex justify="space-between"><Typography.Text type="secondary">0:00</Typography.Text><Typography.Text type="secondary">{buffer.duration.toFixed(2)} s</Typography.Text></Flex>
  </div>;
}
