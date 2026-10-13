import shutil
import subprocess
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise FFmpegError("ffmpeg is not installed or not on PATH. Install FFmpeg before running video generation/concatenation.")


def run_ffmpeg(args: list[str]) -> None:
    require_ffmpeg()
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr[-4000:])


def extract_reference_clip(input_video: Path, output_video: Path, seconds: int) -> Path:
    """Create a short, fal-friendly MP4 reference clip from the uploaded source video."""
    output_video.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_video),
            "-t",
            str(seconds),
            "-vf",
            "scale='min(1280,iw)':-2,fps=24,format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-threads",
            "2",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output_video),
        ]
    )
    return output_video


def concat_videos(segment_paths: list[Path], output_video: Path) -> Path:
    output_video.parent.mkdir(parents=True, exist_ok=True)
    if not segment_paths:
        raise ValueError("No segment videos to concatenate.")
    if len(segment_paths) == 1:
        shutil.copyfile(segment_paths[0], output_video)
        return output_video

    list_file = output_video.parent / f"{output_video.stem}_concat.txt"
    lines = []
    for path in segment_paths:
        safe = str(path.resolve()).replace("'", "'\\''")
        lines.append(f"file '{safe}'")
    list_file.write_text("\n".join(lines), encoding="utf-8")

    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-threads",
            "2",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output_video),
        ]
    )
    return output_video


def generate_mock_video(output_video: Path, duration: int, label: str, seed: int = 0) -> Path:
    output_video.parent.mkdir(parents=True, exist_ok=True)
    colors = ["#1f2937", "#374151", "#4b5563", "#6b7280", "#111827"]
    color = colors[seed % len(colors)]
    frequency = 330 + (seed % 8) * 55
    escaped_label = label.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")[:80]
    drawtext = (
        f"drawtext=text='{escaped_label}':fontcolor=white:fontsize=36:"
        "x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.45:boxborderw=20"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s=1280x720:d={duration}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={frequency}:duration={duration}",
        "-vf",
        drawtext,
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-threads",
        "2",
        "-c:a",
        "aac",
        "-shortest",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_video),
    ]
    try:
        run_ffmpeg(cmd)
    except FFmpegError:
        # Some FFmpeg builds lack drawtext support. Fall back to plain color + tone.
        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=1280x720:d={duration}",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={frequency}:duration={duration}",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-threads",
                "2",
                "-c:a",
                "aac",
                "-shortest",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output_video),
            ]
        )
    return output_video
