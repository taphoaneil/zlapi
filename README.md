# zlapi 1.3.0

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
pip install git+https://github.com/taphoaneil/zlapi.git@v1.3.0
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

## Thay đổi 1.3.0

### Ghim tin nhắn chat riêng 1-1

Các API ghim chat riêng dùng ID của người đối diện. `pinMsg` là
`MessageObject` có đủ `msgType`, `msgId`, `cliMsgId`, `uidFrom`, `dName`
và `content`, chẳng hạn đối tượng nhận qua `onMessage`.

```python
# Ghim không hẹn giờ. Có thể truyền version hiện tại của board nếu đã biết.
created = api.pinUserMsg(pinMsg, userId)

board = api.getUserPinMsg(userId)
for pin in board.data:
    print(pin.id, pin.params)

# "Mới nhất" là mục đầu theo thứ tự Zalo trả về, không sắp xếp theo thời gian.
first = api.getLatestUserPinMsg(userId)  # None nếu không có tin đang ghim

# Gỡ một mục từ danh sách vừa đọc; version thuộc board, không phải createTime.
if board.data:
    result = api.unpinUserMsg(board.data[0].id, board.version, userId)
```

`getUserPinMsg` trả `User(data=[...], version=...)`, chỉ gồm tin ghim
(`type=2`) và giữ thứ tự máy chủ. Bản ghi và `params` dạng JSON được giải mã
để truy cập bằng thuộc tính. Kết quả tạo ghim giữ `data` và `version` của
máy chủ; kết quả gỡ ghim cũng giữ phiên bản mới. Lỗi API, gồm lỗi phiên bản
cũ, phát sinh `ZaloAPIException`; hãy đọc lại danh sách trước khi thử lại.

Khi `listen()` đang chạy, ghim/gỡ ghim 1-1 đi vào **`onMessage`**:

```python
from zlapi import ZaloAPI
from zlapi.models import EventType, ThreadType

class Bot(ZaloAPI):
    def onMessage(self, mid, author_id, message, message_object,
                  thread_id, thread_type):
        event_type = getattr(message_object, "event_type", None)
        if thread_type == ThreadType.USER and event_type in (
            EventType.NEW_PIN_TOPIC, EventType.UNPIN_TOPIC,
        ):
            event = message_object.event_data  # cũng là tham số message
            print(event_type, thread_id, author_id, event.topic, event.version)
            return
        # Xử lý tin nhắn thông thường ở đây.
```

`thread_id` là `conversationId`, `author_id` là người thực hiện (`actorId`).
`mid` là ID của control nếu có, nếu thiếu là `None`; không dùng nó làm ID
tin được ghim. `message_object` giữ control gốc và thêm `event_type`,
`event_data`. Với ghim mới, tin nguồn nằm trong `event.topic.params`;
với gỡ ghim, máy chủ có thể chỉ gửi `topicId` và `topicType`.

Callback nhận cả thao tác của mình và người đối diện từ WebSocket. Gọi API
thành công không tự tạo callback, vì vậy không phát sinh bản sao từ response.
Sự kiện ghim nhóm vẫn dùng `GroupEventType` qua `onEvent`. Các API này chưa
bổ sung ghim Cloud, hẹn giờ hay sắp xếp lại danh sách ghim.

## Thay đổi 1.2.2

- **Ghim tin nhắn nhóm:** dùng payload board hiện tại của Zalo cho ghim không hẹn giờ (`duration: 0`), thay vì các trường legacy không còn được endpoint chấp nhận.
- **Gỡ ghim:** dùng bản ghi board hiện tại (`id`, `params`, `createTime`) để gọi `unpinv2` đúng `topicId` và `boardVersion`.
- **Gửi tin nhắn nhóm:** khi API chỉ trả `msgId`, `sendMessage` trả thêm chính `clientId` của request làm `cliMsgId`; ứng dụng vì vậy vẫn ghim được tin vừa gửi.

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
