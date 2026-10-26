from app.application.use_cases.process_video_frames import _analysis_frame_step


def test_frame_step_skips_frames_only_for_high_fps_videos():
    assert _analysis_frame_step(None) == 1
    assert _analysis_frame_step(24) == 1
    assert _analysis_frame_step(30) == 1
    assert _analysis_frame_step(59.94) == 2
    assert _analysis_frame_step(120) == 6

