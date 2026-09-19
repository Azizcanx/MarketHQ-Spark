import os
import sys
import json
import math
import subprocess
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

import cv2


# ============================================================
# PATH / CONFIG
# ============================================================

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

VIDEO_DIR = os.path.join(
    PROJECT_ROOT,
    "videos"
)

OUTPUT_DIR = os.path.join(
    PROJECT_ROOT,
    "video_analysis"
)

FRAME_DIR = os.path.join(
    OUTPUT_DIR,
    "frames"
)

REPORT_DIR = os.path.join(
    OUTPUT_DIR,
    "reports"
)


# ============================================================
# FRAME ANALYSIS CONFIG
# ============================================================

# Sabit örnekleme aralığı.
# Çok küçük tutarsak gereksiz frame sayısı artar.
SAMPLE_INTERVAL_SECONDS = 2.0

# Benzer kareleri azaltmak için minimum zaman.
MIN_SELECTED_FRAME_GAP = 1.5

# Scene change eşiği.
# Düşük = daha hassas, daha fazla frame.
SCENE_CHANGE_THRESHOLD = 0.16

# Görüntü benzerliği için threshold.
SIMILARITY_THRESHOLD = 0.94

# Çok küçük veya çok büyük tek renkli / boş ekranları ele.
MIN_EDGE_DENSITY = 0.015
MAX_EDGE_DENSITY = 0.60

# Grafikte yatay/dikey çizgi yoğunluğu.
MIN_LINE_DENSITY = 0.008

# Kaydedilecek maksimum frame.
# İlk sürümde maliyet ve disk kullanımını kontrol ediyoruz.
MAX_SELECTED_FRAMES = 300


# ============================================================
# DIRECTORY
# ============================================================

def ensure_directories() -> None:

    os.makedirs(
        VIDEO_DIR,
        exist_ok=True
    )

    os.makedirs(
        FRAME_DIR,
        exist_ok=True
    )

    os.makedirs(
        REPORT_DIR,
        exist_ok=True
    )


# ============================================================
# BASIC HELPERS
# ============================================================

def format_timestamp(
    seconds: float
) -> str:

    seconds = max(
        0.0,
        float(seconds)
    )

    td = timedelta(
        seconds=seconds
    )

    total_seconds = int(
        td.total_seconds()
    )

    hours = total_seconds // 3600
    minutes = (
        total_seconds % 3600
    ) // 60
    secs = total_seconds % 60

    milliseconds = int(
        (seconds - int(seconds))
        * 1000
    )

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{secs:02d}."
        f"{milliseconds:03d}"
    )


def clamp(
    value: float,
    low: float,
    high: float
) -> float:

    return max(
        low,
        min(
            high,
            value
        )
    )


# ============================================================
# VIDEO INFORMATION
# ============================================================

def get_video_info(
    video_path: str
) -> Dict[str, Any]:

    capture = cv2.VideoCapture(
        video_path
    )

    if not capture.isOpened():

        raise RuntimeError(
            f"Video açılamadı: {video_path}"
        )

    fps = capture.get(
        cv2.CAP_PROP_FPS
    )

    frame_count = int(
        capture.get(
            cv2.CAP_PROP_FRAME_COUNT
        )
    )

    width = int(
        capture.get(
            cv2.CAP_PROP_FRAME_WIDTH
        )
    )

    height = int(
        capture.get(
            cv2.CAP_PROP_FRAME_HEIGHT
        )
    )

    duration = 0.0

    if fps and fps > 0:
        duration = (
            frame_count / fps
        )

    capture.release()

    return {
        "path": video_path,
        "filename": os.path.basename(
            video_path
        ),
        "fps": fps,
        "frame_count": frame_count,
        "width": width,
        "height": height,
        "duration_seconds": duration,
        "duration": format_timestamp(
            duration
        ),
    }


# ============================================================
# IMAGE METRICS
# ============================================================

def compute_gray_difference(
    previous_gray,
    current_gray
) -> float:

    previous = cv2.resize(
        previous_gray,
        (320, 180)
    )

    current = cv2.resize(
        current_gray,
        (320, 180)
    )

    previous = previous.astype(
        "float32"
    )

    current = current.astype(
        "float32"
    )

    difference = cv2.absdiff(
        previous,
        current
    )

    return float(
        difference.mean()
        / 255.0
    )


def compute_histogram_similarity(
    previous_frame,
    current_frame
) -> float:

    previous_hsv = cv2.cvtColor(
        previous_frame,
        cv2.COLOR_BGR2HSV
    )

    current_hsv = cv2.cvtColor(
        current_frame,
        cv2.COLOR_BGR2HSV
    )

    hist_previous = cv2.calcHist(
        [previous_hsv],
        [0, 1],
        None,
        [32, 32],
        [0, 180, 0, 256]
    )

    hist_current = cv2.calcHist(
        [current_hsv],
        [0, 1],
        None,
        [32, 32],
        [0, 180, 0, 256]
    )

    cv2.normalize(
        hist_previous,
        hist_previous
    )

    cv2.normalize(
        hist_current,
        hist_current
    )

    similarity = cv2.compareHist(
        hist_previous,
        hist_current,
        cv2.HISTCMP_CORREL
    )

    return float(
        clamp(
            (similarity + 1.0) / 2.0,
            0.0,
            1.0
        )
    )


def compute_edge_density(
    frame
) -> float:

    gray = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )

    edges = cv2.Canny(
        gray,
        80,
        180
    )

    edge_pixels = cv2.countNonZero(
        edges
    )

    total_pixels = (
        edges.shape[0]
        * edges.shape[1]
    )

    if total_pixels <= 0:
        return 0.0

    return (
        edge_pixels
        / total_pixels
    )


def compute_line_density(
    frame
) -> float:

    gray = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )

    gray = cv2.resize(
        gray,
        (640, 360)
    )

    edges = cv2.Canny(
        gray,
        70,
        150
    )

    lines = cv2.HoughLinesP(
        edges,
        1,
        math.pi / 180,
        threshold=45,
        minLineLength=60,
        maxLineGap=10
    )

    if lines is None:
        return 0.0

    image_area = (
        gray.shape[0]
        * gray.shape[1]
    )

    approximate_line_length = 0.0

    for line in lines:

        x1, y1, x2, y2 = (
            line[0]
        )

        length = math.sqrt(
            (x2 - x1) ** 2
            + (y2 - y1) ** 2
        )

        approximate_line_length += (
            length
        )

    if image_area <= 0:
        return 0.0

    return (
        approximate_line_length
        / image_area
    )


def compute_color_activity(
    frame
) -> float:

    hsv = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2HSV
    )

    saturation = hsv[
        :,
        :,
        1
    ]

    return float(
        saturation.mean()
        / 255.0
    )


# ============================================================
# GRAPHIC LIKELIHOOD
# ============================================================

def estimate_chart_likelihood(
    frame
) -> Dict[str, float]:

    edge_density = (
        compute_edge_density(
            frame
        )
    )

    line_density = (
        compute_line_density(
            frame
        )
    )

    color_activity = (
        compute_color_activity(
            frame
        )
    )

    # Grafik ekranlarında genellikle:
    # - yüksek ama aşırı olmayan çizgi yoğunluğu
    # - belirli miktarda kenar
    # - düşük/orta renk yoğunluğu
    # görülür.
    #
    # Bu yalnızca HEURISTIC bir skor.
    # Kesin chart detection değildir.

    edge_score = clamp(
        edge_density / 0.10,
        0.0,
        1.0
    )

    line_score = clamp(
        line_density / 0.04,
        0.0,
        1.0
    )

    color_score = clamp(
        color_activity / 0.50,
        0.0,
        1.0
    )

    chart_score = (
        edge_score * 0.35
        + line_score * 0.45
        + color_score * 0.20
    )

    # Boş ekran / çok yoğun görüntüler için ceza.
    if edge_density < MIN_EDGE_DENSITY:
        chart_score *= 0.25

    if edge_density > MAX_EDGE_DENSITY:
        chart_score *= 0.55

    return {
        "chart_likelihood": clamp(
            chart_score,
            0.0,
            1.0
        ),

        "edge_density": edge_density,

        "line_density": line_density,

        "color_activity": color_activity,
    }


# ============================================================
# FRAME QUALITY
# ============================================================

def compute_blur_score(
    frame
) -> float:

    gray = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )

    variance = cv2.Laplacian(
        gray,
        cv2.CV_64F
    ).var()

    # 0-1 aralığına sıkıştırılmış kalite.
    return clamp(
        variance / 500.0,
        0.0,
        1.0
    )


def compute_brightness(
    frame
) -> float:

    gray = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )

    return float(
        gray.mean()
        / 255.0
    )


# ============================================================
# FRAME SCORE
# ============================================================

def score_frame(
    frame,
    scene_change_score: float
) -> Dict[str, Any]:

    chart = estimate_chart_likelihood(
        frame
    )

    blur_score = compute_blur_score(
        frame
    )

    brightness = compute_brightness(
        frame
    )

    # Çok karanlık veya aşırı aydınlık görüntüler
    # biraz cezalandırılır.
    brightness_quality = 1.0

    if brightness < 0.08:
        brightness_quality = 0.40

    elif brightness > 0.95:
        brightness_quality = 0.55

    final_score = (
        chart["chart_likelihood"] * 0.55
        + blur_score * 0.20
        + scene_change_score * 0.15
        + brightness_quality * 0.10
    )

    return {
        **chart,

        "blur_score": blur_score,

        "brightness": brightness,

        "brightness_quality": (
            brightness_quality
        ),

        "scene_change_score": (
            scene_change_score
        ),

        "final_score": clamp(
            final_score,
            0.0,
            1.0
        ),
    }


# ============================================================
# FRAME SAVE
# ============================================================

def safe_filename(
    value: str
) -> str:

    invalid = [
        "<",
        ">",
        ":",
        '"',
        "/",
        "\\",
        "|",
        "?",
        "*",
    ]

    for char in invalid:
        value = value.replace(
            char,
            "_"
        )

    return value


def save_frame(
    frame,
    video_name: str,
    timestamp: float,
    index: int
) -> str:

    base = os.path.splitext(
        os.path.basename(
            video_name
        )
    )[0]

    timestamp_string = format_timestamp(
        timestamp
    ).replace(
        ":",
        "-"
    ).replace(
        ".",
        "_"
    )

    filename = safe_filename(
        f"{base}__"
        f"{index:04d}__"
        f"{timestamp_string}.jpg"
    )

    output_path = os.path.join(
        FRAME_DIR,
        filename
    )

    cv2.imwrite(
        output_path,
        frame,
        [
            cv2.IMWRITE_JPEG_QUALITY,
            92
        ]
    )

    return output_path


# ============================================================
# DUPLICATE REDUCTION
# ============================================================

def frames_are_similar(
    previous_frame,
    current_frame
) -> bool:

    similarity = (
        compute_histogram_similarity(
            previous_frame,
            current_frame
        )
    )

    return (
        similarity >=
        SIMILARITY_THRESHOLD
    )


# ============================================================
# VIDEO SCANNER
# ============================================================

def scan_video(
    video_path: str
) -> Dict[str, Any]:

    info = get_video_info(
        video_path
    )

    print(
        f"Video: {info['filename']}"
    )

    print(
        f"Süre: {info['duration']}"
    )

    print(
        f"FPS: {info['fps']:.2f}"
    )

    print(
        f"Çözünürlük: "
        f"{info['width']}x{info['height']}"
    )

    capture = cv2.VideoCapture(
        video_path
    )

    if not capture.isOpened():

        raise RuntimeError(
            "Video açılamadı."
        )

    fps = info["fps"]

    if not fps or fps <= 0:
        fps = 30.0

    total_frames = info[
        "frame_count"
    ]

    sample_step = max(
        1,
        int(
            fps
            * SAMPLE_INTERVAL_SECONDS
        )
    )

    selected_frames = []

    previous_frame = None
    previous_gray = None

    frame_number = 0

    candidate_count = 0
    sampled_count = 0

    last_selected_timestamp = (
        -MIN_SELECTED_FRAME_GAP
    )

    while True:

        success, frame = capture.read()

        if not success:
            break

        current_frame_number = (
            frame_number
        )

        frame_number += 1

        if (
            current_frame_number
            % sample_step
            != 0
        ):

            continue

        sampled_count += 1

        timestamp = (
            current_frame_number
            / fps
        )

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )

        if previous_frame is None:

            scene_change_score = 0.0

        else:

            diff = (
                compute_gray_difference(
                    previous_gray,
                    gray
                )
            )

            # Ortalama piksel farkını
            # scene-change skoruna dönüştür.
            scene_change_score = clamp(
                diff / 0.35,
                0.0,
                1.0
            )

        frame_metrics = score_frame(
            frame,
            scene_change_score
        )

        chart_likelihood = (
            frame_metrics[
                "chart_likelihood"
            ]
        )

        scene_changed = (
            scene_change_score
            >= SCENE_CHANGE_THRESHOLD
        )

        chart_candidate = (
            chart_likelihood >= 0.32
        )

        if (
            chart_candidate
            or scene_changed
        ):

            candidate_count += 1

            too_close = (
                timestamp
                - last_selected_timestamp
                < MIN_SELECTED_FRAME_GAP
            )

            duplicate = False

            if selected_frames:

                previous_saved = (
                    selected_frames[-1]
                )

                previous_frame_path = (
                    previous_saved[
                        "frame_path"
                    ]
                )

                previous_image = cv2.imread(
                    previous_frame_path
                )

                if previous_image is not None:

                    try:

                        duplicate = (
                            frames_are_similar(
                                previous_image,
                                frame
                            )
                        )

                    except Exception:

                        duplicate = False

            should_select = (
                not too_close
                and not duplicate
            )

            # Scene change tek başına yeterli olabilir,
            # fakat düşük kaliteli frame'leri seçmeyelim.
            if (
                should_select
                and (
                    chart_likelihood >= 0.32
                    or (
                        scene_changed
                        and frame_metrics[
                            "blur_score"
                        ] >= 0.15
                    )
                )
            ):

                frame_path = save_frame(
                    frame,
                    info["filename"],
                    timestamp,
                    len(
                        selected_frames
                    ) + 1
                )

                selected_frames.append(
                    {
                        "index": len(
                            selected_frames
                        ) + 1,

                        "timestamp_seconds": (
                            timestamp
                        ),

                        "timestamp": (
                            format_timestamp(
                                timestamp
                            )
                        ),

                        "frame_path": (
                            frame_path
                        ),

                        "scene_changed": (
                            scene_changed
                        ),

                        "scene_change_score": (
                            round(
                                scene_change_score,
                                4
                            )
                        ),

                        "chart_likelihood": (
                            round(
                                chart_likelihood,
                                4
                            )
                        ),

                        "blur_score": (
                            round(
                                frame_metrics[
                                    "blur_score"
                                ],
                                4
                            )
                        ),

                        "edge_density": (
                            round(
                                frame_metrics[
                                    "edge_density"
                                ],
                                4
                            )
                        ),

                        "line_density": (
                            round(
                                frame_metrics[
                                    "line_density"
                                ],
                                4
                            )
                        ),

                        "brightness": (
                            round(
                                frame_metrics[
                                    "brightness"
                                ],
                                4
                            )
                        ),

                        "final_score": (
                            round(
                                frame_metrics[
                                    "final_score"
                                ],
                                4
                            )
                        ),
                    }
                )

                last_selected_timestamp = (
                    timestamp
                )

                if len(
                    selected_frames
                ) >= MAX_SELECTED_FRAMES:

                    break

        previous_frame = frame
        previous_gray = gray

        if (
            sampled_count % 100 == 0
        ):

            progress = 0.0

            if total_frames > 0:
                progress = (
                    current_frame_number
                    / total_frames
                    * 100
                )

            print(
                f"  Tarama: "
                f"{progress:.1f}% | "
                f"Aday: "
                f"{len(selected_frames)}"
            )

    capture.release()

    print()
    print(
        f"Örneklenen frame: "
        f"{sampled_count}"
    )

    print(
        f"Grafik/sahne adayı: "
        f"{candidate_count}"
    )

    print(
        f"Seçilen frame: "
        f"{len(selected_frames)}"
    )

    return {
        "video": info,
        "sampling": {
            "sample_interval_seconds": (
                SAMPLE_INTERVAL_SECONDS
            ),

            "sampled_frames": (
                sampled_count
            ),

            "candidate_frames": (
                candidate_count
            ),

            "selected_frames": (
                len(selected_frames)
            ),
        },

        "frames": selected_frames,
    }


# ============================================================
# REPORT SAVE
# ============================================================

def save_report(
    report: Dict[str, Any]
) -> str:

    video_name = report[
        "video"
    ]["filename"]

    base = os.path.splitext(
        video_name
    )[0]

    filename = (
        safe_filename(
            base
        )
        + "__chart_scan.json"
    )

    path = os.path.join(
        REPORT_DIR,
        filename
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            report,
            file,
            ensure_ascii=False,
            indent=2
        )

    return path


# ============================================================
# SELECT VIDEO
# ============================================================

def find_videos() -> List[str]:

    if not os.path.exists(
        VIDEO_DIR
    ):
        return []

    supported = {
        ".mp4",
        ".mkv",
        ".mov",
        ".avi",
        ".webm",
        ".m4v",
    }

    videos = []

    for filename in os.listdir(
        VIDEO_DIR
    ):

        path = os.path.join(
            VIDEO_DIR,
            filename
        )

        if not os.path.isfile(
            path
        ):
            continue

        extension = (
            os.path.splitext(
                filename
            )[1]
            .lower()
        )

        if extension in supported:
            videos.append(
                path
            )

    videos.sort()

    return videos


def choose_video(
    videos: List[str]
) -> Optional[str]:

    if not videos:
        return None

    if len(videos) == 1:
        return videos[0]

    print()
    print(
        "Bulunan videolar:"
    )

    for index, video in enumerate(
        videos,
        start=1
    ):

        print(
            f"{index}. "
            f"{os.path.basename(video)}"
        )

    print()

    while True:

        choice = input(
            "Video numarası: "
        ).strip()

        try:

            index = int(
                choice
            )

        except ValueError:

            print(
                "Geçerli bir sayı gir."
            )

            continue

        if (
            1 <= index <= len(videos)
        ):

            return videos[
                index - 1
            ]

        print(
            "Geçersiz seçim."
        )


# ============================================================
# SUMMARY
# ============================================================

def print_summary(
    report: Dict[str, Any]
) -> None:

    info = report[
        "video"
    ]

    sampling = report[
        "sampling"
    ]

    frames = report[
        "frames"
    ]

    print()
    print("=========================================")
    print("🎥 VIDEO CHART ENGINE SONUCU")
    print("=========================================")

    print(
        f"Video: "
        f"{info['filename']}"
    )

    print(
        f"Süre: "
        f"{info['duration']}"
    )

    print(
        f"Örneklenen frame: "
        f"{sampling['sampled_frames']}"
    )

    print(
        f"Aday frame: "
        f"{sampling['candidate_frames']}"
    )

    print(
        f"Seçilen frame: "
        f"{sampling['selected_frames']}"
    )

    print()

    if frames:

        top_frames = sorted(
            frames,
            key=lambda item: (
                item["final_score"]
            ),
            reverse=True
        )[:10]

        print(
            "EN GÜÇLÜ FRAME'LER"
        )

        print(
            "-----------------------------------------"
        )

        for frame in top_frames:

            print(
                f"{frame['index']:03d} | "
                f"{frame['timestamp']} | "
                f"chart="
                f"{frame['chart_likelihood']:.2f} | "
                f"score="
                f"{frame['final_score']:.2f}"
            )

    else:

        print(
            "⚠️ Grafik adayı frame bulunamadı."
        )

    print()
    print(
        "========================================="
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print("=========================================")
    print("🎥 FIN[SYS] VIDEO CHART ENGINE")
    print("=========================================")

    print(
        "Bu sürüm: "
        "yerel video + scene detection + "
        "chart heuristic"
    )

    print(
        "API kullanımı: 0"
    )

    print()

    ensure_directories()

    videos = find_videos()

    if not videos:

        print(
            "❌ videos klasöründe video bulunamadı."
        )

        print()
        print(
            f"Video klasörü:"
        )

        print(
            VIDEO_DIR
        )

        print()
        print(
            "Bir video dosyasını bu klasöre koyup "
            "programı tekrar çalıştır."
        )

        return

    video_path = choose_video(
        videos
    )

    if not video_path:

        print(
            "❌ Video seçilemedi."
        )

        return

    print()
    print(
        f"Seçilen: "
        f"{os.path.basename(video_path)}"
    )

    print()

    try:

        report = scan_video(
            video_path
        )

    except Exception as exc:

        print(
            "❌ Video analizi başarısız:"
        )

        print(
            exc
        )

        return

    report_path = save_report(
        report
    )

    print_summary(
        report
    )

    print()
    print(
        f"📄 Rapor:"
    )

    print(
        report_path
    )

    print()
    print(
        f"🖼️ Frame klasörü:"
    )

    print(
        FRAME_DIR
    )

    print()
    print(
        "✅ Video Chart Engine tamamlandı."
    )

    print()
    print(
        "Sonraki aşama:"
    )

    print(
        "Seçilen önemli frame'ler Vision ile "
        "analiz edilip timestamp + grafik bulguları "
        "Knowledge Base'e kaydedilecek."
    )


if __name__ == "__main__":
    main()
