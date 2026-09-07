# zlapi 1.2.1

Fork không chính thức của [`zlapi`](https://github.com/Its-VrxxDev/zlapi) — Zalo API (không chính thức) cho Python.

**Không** dùng `pip install zlapi`: lệnh đó cài [gói PyPI của bản gốc](https://pypi.org/project/zlapi/). Fork này chỉ cài từ GitHub (xem bên dưới).

## Nguồn gốc

- Tác giả gốc: **Lê Quốc Việt (Vexx)**
- Repo gốc: [Its-VrxxDev/zlapi](https://github.com/Its-VrxxDev/zlapi) (v1.0.2, đã archive ngày 19/03/2025)
- License: [MIT](LICENSE) — Copyright (c) 2024 Lê Quốc Việt
- PyPI bản gốc: [pypi.org/project/zlapi](https://pypi.org/project/zlapi/)
- Liên hệ tác giả gốc: [Telegram](https://t.me/vrxx1337) · [Facebook](https://www.facebook.com/profile.php?id=100094031375075)

Thư viện này **không** phải API chính thức của Zalo. Cách hoạt động có thể không tuân thủ Điều khoản dịch vụ của Zalo; tác giả gốc và fork không chịu trách nhiệm nếu tài khoản bị khóa.

## Cài đặt

```bash
pip uninstall zlapi -y
pip install git+https://github.com/taphoaneil/zlapi.git
```

Nhánh hoặc tag:

```bash
pip install git+https://github.com/taphoaneil/zlapi.git@master
pip install git+https://github.com/taphoaneil/zlapi.git@v1.2.1
```

Trong `requirements.txt` của ứng dụng:

```
zlapi @ git+https://github.com/taphoaneil/zlapi.git@master
```

```python
from zlapi import ZaloAPI, ImageGroup, MultiImageSendResult
```

## My Documents / Cloud

Sau khi đăng nhập, `api.cloud_id` là định danh **My Documents** do máy chủ Zalo
trả về (`send2me_id`); nó không được suy ra từ UID tài khoản. Gửi vào My
Documents bằng `ThreadType.CLOUD` không cần truyền `thread_id`:

```python
from zlapi.models import Message, ThreadType

api.send(Message(text="Ghi chú cho chính mình"), thread_type=ThreadType.CLOUD)
```

Các callback `onMessage` thuộc My Documents cũng nhận
`thread_type=ThreadType.CLOUD`. Nếu phiên đăng nhập không trả về
`send2me_id`, thao tác Cloud sẽ báo lỗi thay vì gửi nhầm sang UID tài khoản.

## Thay đổi 1.2.1

- **Protocol Zalo Web:** `zpw_ver` và login `client_version` lên **647**; hằng số `ZPW_VER` / `ZPW_TYPE` trong `_util` dùng chung cho login và mọi request API.

## Thay đổi 1.2.0

- **My Documents / Cloud:** thêm `ThreadType.CLOUD`; dùng `send2me_id` do Zalo trả về thay vì đoán từ UID tài khoản. Gửi vào My Documents không cần `thread_id`; listener phân loại sự kiện Cloud riêng.
- **Session:** constructor giờ nạp `cookies=` ngay cả khi `auto_login=False`, thuận tiện cho luồng `set session` rồi `login(imei=...)`.

## Thay đổi 1.1.0 so với bản gốc 1.0.2

- **Album ảnh đến:** gom tin có `is_group_layout` / `isGroupLayout`, gọi `onMessage` một lần với `ImageGroup` (ảnh đúng thứ tự hiển thị). Cache album 15 phút, tối đa 1024 album.
- **Gửi nhiều ảnh:** `sendMultiLocalImage` gắn `groupLayoutId`, đọc kích thước bằng Pillow, trả `MultiImageSendResult` (`sent` / `failed` với `ImageSendFailure`).
- **Session:** constructor nhận `cookies=` (không còn `session_cookies=`). Chỉ set cookie chưa bind IMEI/websocket; cần `login(imei=...)`.
- **Reply:** `replyTo(...)` thay cho `replyMessage`.
- **Phụ thuộc:** `requests`, `websocket-client`, `pycryptodome`, `munch`, `Pillow`.
- **Bỏ** `zlapi.Async` và `zlapi.simple`; chỉ còn client đồng bộ.
- **Listen:** websocket qua `websocket-client`; `listen(thread=, reconnect=)` — không còn `type="requests"` hay `run_forever`.
