window.makeRecoveryFixture = async function (family, seed) {
  const width = family === "non_square" ? 29 + seed % 3 : 24;
  const height = family === "non_square" ? 17 : 24;
  const count = seed === 17 ? 6 : 9;
  const fps = seed === 17 ? 8 : 13;
  const layered = family === "opacity" || family === "qualification";
  const layers = [];
  for (let layerIndex = 0; layerIndex < (layered ? 3 : 1); layerIndex++) {
    const layer = new pskl.model.Layer("Explorer " + layerIndex);
    layer.setOpacity(layerIndex === 1 ? 0.5 : layerIndex === 2 ? 0.75 : 1);
    for (let i = 0; i < count; i++) {
      const frame = new pskl.model.Frame(width, height);
      const x0 = 3 + (i + seed) % 8;
      const y0 = 4 + layerIndex;
      for (let y = 0; y < 9; y++) {
        for (let x = 0; x < 10; x++) {
          const body = y > 1 && y < 7 && x > 0 && x < 9;
          const antenna = x === 5 && y < 2;
          const feet = y >= 7 && ((x + i) % 4 === 0);
          if (body || antenna || feet) {
            const hue = (seed * 3 + layerIndex * 73 + i * 11) % 200;
            const color = (x === 3 || x === 7) && y === 3 ? "#ffffff" : `rgb(${hue + 40},${180 - layerIndex * 30},${80 + i * 12})`;
            frame.setPixel(x + x0, y + y0, color);
          }
        }
      }
      frame.setPixel(i % width, height - 1, "#ff00ff");
      layer.addFrame(frame);
    }
    layers.push(layer);
  }
  const model = pskl.model.Piskel.fromLayers(layers, fps, new pskl.model.piskel.Descriptor("Signal explorer", "Original benchmark artwork"));
  model.hiddenFrames = family === "hidden" ? [1, count - 2] : [];
  const controller = pskl.app.piskelController;
  controller.setPiskel(model);
  const saved = JSON.parse(pskl.utils.serialization.Serializer.serialize(model));
  saved.piskel.layers = saved.piskel.layers.map((serialized, layerIndex) => {
    const data = JSON.parse(serialized);
    if (family === "chunks") {
      data.chunks = [];
      for (let offset = 0; offset < count; offset += 2) {
        const frames = layers[layerIndex].getFrames().slice(offset, offset + 2);
        data.chunks.push({layout: frames.map((_, i) => [i + offset]), base64PNG: pskl.utils.serialization.Serializer.serializeFramesToBase64(frames)});
      }
      data.chunks.reverse();
    }
    if (family === "legacy") {
      data.base64PNG = data.chunks[0].base64PNG;
      delete data.chunks;
    }
    return JSON.stringify(data);
  });
  const restored = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Piskel fixture roundtrip timed out")), 10000);
    pskl.utils.serialization.Deserializer.deserialize(saved, value => { clearTimeout(timer); resolve(value); }, reject);
  });
  controller.setPiskel(restored);
  const frames = Array.from({length: count}, (_, i) => controller.renderFrameAt(i, true).toDataURL("image/png"));
  return {
    saved, frames,
    layers: restored.getLayers().map(layer => layer.getFrames().map(frame => pskl.utils.FrameUtils.toImage(frame).toDataURL("image/png"))),
    width: restored.getWidth(), height: restored.getHeight(), fps: controller.getFPS(),
    frame_count: controller.getFrameCount(), hidden_frames: restored.hiddenFrames,
    playback_order: controller.getVisibleFrameIndexes(),
    layer_opacities: restored.getLayers().map(layer => layer.getOpacity()),
  };
};
