"""Create small synthetic media fixtures without downloading external content."""

import argparse
from pathlib import Path
import wave


def make_fixtures(directory):
    import av
    import numpy as np
    from PIL import Image, ImageDraw

    directory = Path(directory)
    paths = [directory / name for name in ("red-circle.png", "tone.wav", "moving-circle.mp4")]
    if any(path.exists() for path in paths):
        raise FileExistsError("A fixture already exists. Choose a new --output directory.")
    directory.mkdir(parents=True, exist_ok=True)

    def picture(center_x):
        image = Image.new("RGB", (256, 256), "white")
        ImageDraw.Draw(image).ellipse((center_x - 35, 93, center_x + 35, 163), fill="red")
        return image

    picture(128).save(paths[0])
    rate = 16000
    times = np.arange(3 * rate) / rate
    # Three short 440 Hz tones, separated by silence. This is not recorded speech.
    phase = times % 1.0
    envelope = np.where(phase < 0.5, np.sin(np.pi * phase / 0.5) ** 2, 0.0)
    samples = (0.3 * np.sin(2 * np.pi * 440 * times) * envelope * 32767).astype("<i2")
    with wave.open(str(paths[1]), "wb") as output:
        output.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        output.writeframes(samples.tobytes())
    with av.open(str(paths[2]), mode="w") as output:
        stream = output.add_stream("mpeg4", rate=4)
        stream.width = stream.height = 256
        stream.pix_fmt = "yuv420p"
        for i in range(16):
            frame = av.VideoFrame.from_image(picture(40 + i * 11))
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)
    for path in paths:
        print(path.resolve())
    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="demo-media")
    make_fixtures(parser.parse_args().output)
