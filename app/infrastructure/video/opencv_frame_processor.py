def _transcode_for_browser(video_path: str) -> bool:
    """Convert unsupported phone codecs/containers to browser H.264 MP4."""
    source = Path(video_path)
    if not source.is_file():
        return False

    fd, temp_name = tempfile.mkstemp(suffix=".mp4", dir=str(source.parent))
    os.close(fd)
    temp_path = Path(temp_name)

    command = [
        "ffmpeg", "-y", "-v", "error", "-i", str(source),
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "128k", str(temp_path),
    ]
    try:
        completed = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False)
        if completed.returncode != 0 or temp_path.stat().st_size <= 0:
            temp_path.unlink(missing_ok=True)
            return False
        os.replace(temp_path, source)
        return True
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        temp_path.unlink(missing_ok=True)
        return False
