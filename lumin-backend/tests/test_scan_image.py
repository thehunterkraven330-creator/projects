import cv2
import numpy as np

from app import visual_index


def _item(colour, bg=(240, 240, 240)):
    im = np.full((400, 400, 3), bg, np.uint8)
    cv2.ellipse(im, (200, 250), (150, 60), 0, 0, 360, colour, -1)
    cv2.rectangle(im, (120, 150), (260, 250), colour, -1)
    return im


def test_the_same_item_photographed_again_is_the_closest():
    red, blue = visual_index.colour_descriptor(_item((40, 40, 220))), visual_index.colour_descriptor(_item((220, 80, 40)))
    again = cv2.resize(_item((45, 45, 215), bg=(225, 230, 235)), (300, 300))
    ok, buf = cv2.imencode(".jpg", again, [cv2.IMWRITE_JPEG_QUALITY, 50])
    q = visual_index.colour_descriptor(cv2.imdecode(buf, cv2.IMREAD_COLOR))
    assert float(red @ q) > visual_index.MIN_SIM[visual_index.KIND_COLOUR]
    assert float(red @ q) > float(blue @ q) + 0.1


def test_descriptors_are_unit_length():
    assert abs(float(np.linalg.norm(visual_index.colour_descriptor(_item((10, 200, 10))))) - 1.0) < 1e-4


def test_a_tiny_or_empty_picture_is_not_described():
    assert visual_index.describe(np.zeros((4, 4, 3), np.uint8)) is None


def test_scan_image_rejects_a_file_that_is_not_a_picture(client):
    r = client.post("/scan/image", files={"image": ("x.jpg", b"not a picture", "image/jpeg")})
    assert r.status_code == 400


def test_scan_image_with_nothing_indexed_says_not_found(client):
    ok, buf = cv2.imencode(".jpg", _item((40, 40, 220)))
    r = client.post("/scan/image", files={"image": ("x.jpg", buf.tobytes(), "image/jpeg")})
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is False and body["similar"] == []
