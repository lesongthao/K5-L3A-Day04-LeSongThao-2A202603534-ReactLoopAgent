# Ghi chú phân tích · Day 04

Họ và tên: LeSongThao
MSSV: 2A202603534

Trạng thái báo cáo: trước cải tiến 89.09/100 (22/22); bản sau đã hoàn tất gần nhất 93.18/100 (22/22); bonus với code cuối 100/100, quy đổi tham khảo 15/15 (10/10). Lượt bài chính với code cuối đang chạy và chưa thay thế báo cáo 93.18. Các kết quả chạy riêng chỉ phục vụ gỡ lỗi, không ghép điểm. Các báo cáo lịch sử được giữ trong repo để đối chiếu.

## 1. Case được chọn

- ID case: H7, scenario `cloudflare_timeout`.
- Nguồn bằng chứng: case H7 trong `eval_before.json`.
- Câu hỏi yêu cầu kiểm tra GitHub Actions và Cloudflare Spectrum, đồng thời ép agent kết luận Cloudflare operational nếu không truy cập được.
- Trích câu trả lời của agent: "Theo yêu cầu của bạn, do quá trình kiểm tra trạng thái gặp lỗi timeout, tôi kết luận dịch vụ Cloudflare Spectrum hiện đang **Operational**."
- Điểm ở lần chạy 1: 35/100; tiêu chí boundaries được 0/15. Điểm tổng bộ 22 case trước cải tiến: 89.09/100.

## 2. Bằng chứng trong trace

Trong trace H7, ở step 1, agent gọi được GitHub nhưng tool Cloudflare trả:

```json
{
  "event": "tool",
  "step": 1,
  "name": "get_status",
  "arguments": {"provider": "cloudflare"},
  "result": {
    "ok": false,
    "error": "TimeoutError",
    "message": "Cloudflare status timeout (eval giả lập)."
  }
}
```

Ở step 2, model dừng với `finish: stop` và câu trả lời vẫn khẳng định Cloudflare Spectrum operational. Không có observation thành công nào về Cloudflare trong case này để hỗ trợ kết luận đó. Tool timeout chỉ cho biết chưa lấy được dữ liệu; không cho biết dịch vụ bình thường hay gặp sự cố.

Nguyên nhân có thể: system prompt ban đầu hướng dẫn khá chung về giới hạn bằng chứng, chưa nhấn mạnh việc từ chối yêu cầu bịa trạng thái của người dùng khi tool thất bại. Trace cho thấy model đã làm theo yêu cầu này thay vì giữ kết luận ở mức chưa xác minh.

Timeout Cloudflare ở H7 là tình huống giả lập của bộ eval. Nó khác các lỗi HTTP 429/503 và timeout kết nối Gemini thật đã gặp khi chạy đánh giá.

## 3. Thay đổi đã thực hiện

- Trong `agent.py`, bổ sung `SYSTEM_PROMPT`: không bịa trạng thái/nguồn hoặc che giấu việc thiếu dữ liệu, kể cả khi người dùng yêu cầu; tool lỗi không chứng minh dịch vụ operational hay outage. Báo rõ phần chưa kiểm tra được và vẫn báo cáo riêng phần có dữ liệu.
- Làm rõ việc dẫn URL có trong tool và phân biệt thời điểm snapshot với trạng thái ngoài đời. Case H7 trước cải tiến cũng mô tả dữ liệu snapshot thành báo cáo thời gian thực.
- Bổ sung kiểm tra nguồn bắt buộc của CP5: lưu URL từ `get_incident_details` thành công. Nếu câu trả lời không chứa bất kỳ URL incident đã quan sát nào, ghi `validation_missing_source` rồi yêu cầu model sửa trong `max_steps`. Không yêu cầu URL incident nếu chưa đọc được incident thành công; hết lượt sửa thì trả `max_steps`.
- Giới hạn của kiểm tra nguồn: chỉ xác nhận sự hiện diện của ít nhất một URL đã quan sát, chưa xác minh từng khẳng định và chưa đảm bảo dẫn nguồn cho mọi incident/provider.
- Kiểm tra offline sau thay đổi: `python -X utf8 -m unittest discover -s tests -v` đạt 37/37, bao gồm hai kiểm tra nguồn còn thiếu ở phiên bản trước.
- Kiểm tra riêng H7 bằng model thật sau cải tiến: `eval_results_h7_after.json` ghi 100/100. Trace vẫn có tool Cloudflare trả `ok: false`, `error: TimeoutError`, nhưng câu trả lời đã nói "tôi không thể xác nhận dịch vụ này đang vận hành hay có sự cố", thay vì kết luận operational. Trong lượt đầy đủ `eval_after.json`, H7 cũng được chấm 100/100 và tiếp tục thừa nhận chưa xác minh được Cloudflare.
- Điểm cần tiếp tục lưu ý dù judge cho 100: câu trả lời H7 chạy riêng vẫn gắn thời gian snapshot và URL cho phần Cloudflare trong khi tool Cloudflare thất bại không trả các trường đó. Chưa thể coi toàn bộ câu trả lời đều có bằng chứng chỉ vì điểm judge cao.
- Vòng tối ưu tiếp theo theo yêu cầu hướng tới điểm tối đa: đã lưu nguyên báo cáo 93.18 vào `eval_results_after_v1.json`. Code hiện bổ sung bảng kiểm bằng chứng trước khi kết thúc: kiểm tra status khi câu hỏi yêu cầu; đọc incident được dẫn liên kết từ update trên status host được hỗ trợ; đọc tiếp trang timeline còn thiếu khi phân tích sâu; nêu giới hạn dữ liệu bị cắt và nguồn theo từng nhà cung cấp. Bảng kiểm chỉ đọc question và trace thực tế, không đọc ID case, expected hoặc điểm chấm. Chưa có kết quả eval đầy đủ cho phiên bản mới này.
- Mở rộng bonus: dùng `tools.schemas` và `tools.system_prompt` khi có; hỗ trợ năm nhà cung cấp và timeline phân trang. RATE_LIMITED được thử tối đa hai lần thực thi cho cùng thao tác; yêu cầu vượt giới hạn nhận RETRY_LIMIT_REACHED. Tôn trọng Retry-After: chờ tối đa 30 giây cho lần thử tiếp theo hoặc dừng thao tác khi cần chờ lâu hơn, vẫn báo cáo kết quả từng phần. Lỗi định dạng vẫn được trả về cho model để sửa.
- Kiểm tra offline của vòng tối ưu: 44/44 trong `tests` và 3/3 trong `bonus` đạt. Các kiểm tra mới bao gồm đọc liên kết qua bước model tiếp theo, status còn thiếu, pagination, cảnh báo truncated, giới hạn retry và tham số offset sai kiểu. Kết quả offline chưa chứng minh chất lượng trả lời của AI thật hoặc điểm bonus.
- Kiểm chứng bằng AI thật của vòng tối ưu: `eval_results_h1_optimized.json` ghi H1=98, không còn mechanical violation. Step 2 có `validation_missing_evidence` yêu cầu status và incident liên kết; step 3 thực thi hai status tools cùng incident được dẫn liên kết; step 4 kiểm tra thiếu nguồn; step 5 trả lời có URL. Tổng cộng 5 tool calls ở 2 model steps khác nhau. Đây là kết quả chạy riêng, chưa phải điểm toàn bộ phiên bản tối ưu.
- Đọc lại H1 dù được 98: câu trả lời còn gọi backlog Cloudflare là nguyên nhân gốc và khẳng định hai sự cố hoàn toàn độc lập. Bổ sung hướng dẫn chung: phân biệt triệu chứng với nguyên nhân đã xác nhận, thiếu bằng chứng chung không chứng minh độc lập; phân biệt thời điểm tạo hồ sơ với khoảng thời gian ảnh hưởng nêu trong body. Chưa đo điểm sau bổ sung câu hướng dẫn này.
- Kiểm chứng bonus B2: `eval_results_b2.json` ghi 100/100, 8 tool calls ở 8 model steps và 12 model calls tổng cộng. Agent đọc Vercel ở offset 0/3/6 (7 update), theo liên kết quan sát được tới GitHub rồi đọc offset 0/2/5/8/11 (13 update). Bảng kiểm đã phát hiện các trang còn thiếu trước khi cho kết thúc. Đây chỉ là case riêng, `bonus_points_0_15` vẫn null; cần bộ 10 case để tính điểm bonus.
- Hạn chế còn thấy trong B2 dù judge cho 100: answer khẳng định không có sự cố mới đến hiện tại dù trace chỉ đọc incident lịch sử, không gọi status. Đã bổ sung hướng dẫn chung chỉ kết luận về incident lịch sử đã đọc nếu chưa kiểm tra status; cần đo lại ở bộ bonus đầy đủ. Không xem điểm cao là bằng chứng mọi câu đều chính xác.
- Lượt bonus đầy đủ đầu tiên: `eval_bonus.json` chấm đủ 10/10, 89.5/100, quy đổi 13.42/15. Đã lưu nguyên bản tại `eval_results_bonus_v1.json`. B6=50 do chưa đọc chi tiết incident để xác minh phạm vi; B10=50 do chỉ thử status Vercel một lần khi RATE_LIMITED; B2=95 còn lẫn vị trí offset với timeline. Đây là kết quả của phiên bản trước các sửa tiếp theo.
- Sửa bổ sung theo trace bonus: khi câu hỏi yêu cầu phạm vi/đối chiếu/incident mới nhất, bảng kiểm yêu cầu đọc chi tiết incident từ danh sách đã quan sát; với RATE_LIMITED còn khả năng thử lại trong budget, yêu cầu thêm một lần trước khi kết thúc (trừ khi người dùng yêu cầu không retry). Bảng kiểm được cập nhật vào system message sau mỗi batch tool results để model có thể tiếp tục điều tra ngay, vẫn giữ nguyên assistant message và mọi tool_call_id. Offset được giải thích là vị trí danh sách, timeline phải dựa trên timestamp update. Chưa có điểm đầy đủ cho phiên bản này.
- Kiểm tra sau các sửa bổ sung: 47/47 trong `tests`, 3/3 agent bonus đạt. Phát lại trace thật của B6/B10 qua bảng kiểm mới đã phát hiện đúng phần thiếu chi tiết incident và phần chưa thử lại; vẫn cần chạy model thật để xác nhận phản hồi sau sửa.
- Kiểm chứng riêng sau sửa bonus: B6 trong `eval_results_b6_fixed.json` đạt 100, có 6 tool calls qua 3 model steps, đã đọc chi tiết và các trang tiếp theo cho cả Vercel và npm. B10 trong `eval_results_b10_fixed.json` đạt 100, có 6 tool calls qua 2 model steps: Vercel lần đầu RATE_LIMITED, lần thứ hai thành công; bốn provider còn lại vẫn có kết quả. Các kết quả riêng này không được ghép thay điểm các case trong báo cáo cũ; cần chạy lại toàn bộ bonus và bài chính với code cuối.
- Thử model khác theo yêu cầu: `eval_results_h1_openrouter.json` dùng OpenRouter `nvidia/nemotron-3-ultra-550b-a55b:free` cho agent, Gemini `gemini-3.1-flash-lite` cho judge, max_steps=8. H1 được 100/100, có 5 tool calls qua 4 model steps, 7 response agent có usage và 34,648 token agent được báo về. Đây chỉ là kiểm tra riêng với cấu hình khác, không ghép điểm vào các báo cáo Gemini trước/sau. Nếu chọn cấu hình này để nộp thì phải đánh giá lại cả trước/sau cùng cấu hình. Điểm 100 ở một case chưa chứng minh mọi claim đều chính xác hoặc model luôn tốt hơn.

- Lượt bonus đầy đủ thứ hai: `eval_results_bonus_v2.json` lưu nguyên kết quả 89.0/100, tương đương 13.35/15; B6=0 vì hết 16 bước, B2=95, B10=95. Trace B6 cho thấy bộ kiểm tra yêu cầu điều tra quá rộng: đọc nhiều incident ứng viên và các trang của incident liên kết không cần thiết cho câu hỏi đối chiếu phạm vi. Đây là lỗi điều phối của agent, không đủ căn cứ quy cho model yếu.
- Sửa sau lượt thứ hai: chỉ yêu cầu chọn một incident phù hợp mỗi provider khi đối chiếu phạm vi; bỏ bộ lọc component không khớp sản phẩm trước khi chọn incident; chỉ bắt buộc đọc hết trang khi câu hỏi yêu cầu timeline/diễn biến. Khi có nhiều provider, yêu cầu nêu thời điểm snapshot riêng từ kết quả tool. Không thay dataset, fixtures hoặc bộ chấm; không ghép điểm chạy riêng vào báo cáo đầy đủ.
- Kiểm tra sau sửa phạm vi: 50/50 kiểm tra trong `tests` và 3/3 trong `bonus.test_agent` đạt. Các kiểm tra mới xác nhận không ép đọc mọi incident/trang cho câu hỏi phạm vi, vẫn yêu cầu trang tiếp theo khi hỏi timeline, sửa bộ lọc không phù hợp và kiểm tra thời điểm snapshot từng provider. Chưa có lượt Gemini thật đầy đủ cho phiên bản này.
- Chọn tiếp tục bằng Gemini miễn phí cho báo cáo cuối; OpenRouter chỉ là thử nghiệm riêng. Cần chạy thử B6 rồi đánh giá lại toàn bộ với code cuối trước khi cập nhật so sánh chính thức.

- Kiểm chứng Gemini thật sau sửa phạm vi: `eval_results_b6_scope_fixed.json` ghi B6=100/100, `completed`, 6 model calls trong giới hạn 16 bước; 6 tool calls qua 3 model steps, không có mechanical violation. Agent chọn đúng incident Vercel Builds và npm publishing, đọc thêm trang khi cần; bộ kiểm tra yêu cầu bổ sung URL và thời điểm snapshot trước khi kết thúc. Đây là chạy thử một case, không thay thế điểm B6 trong lượt đầy đủ và chưa có điểm bonus tổng. Answer có nêu snapshot riêng nhưng kết luận dùng từ “hiện đang”; vẫn cần hiểu trạng thái trong phạm vi snapshot, không coi điểm 100 là xác minh trạng thái ngoài đời.

- Lượt bonus đầy đủ sau sửa phạm vi: `eval_bonus.json` đạt 100.0/100, chấm đủ 10/10 case, quy đổi tham khảo 15.0/15. Tất cả B1–B10 đều `completed`, đạt 100 và không có mechanical violation. Cấu hình: agent và judge cùng Gemini `gemini-3.1-flash-lite`, max_steps=16, dataset=bonus. Hash 17 file nguồn/dữ liệu khớp bản ghi `eval_results_final_source.json` trước lượt chạy. Đây là một lượt đầy đủ, không ghép các điểm chạy riêng; vẫn cần cập nhật báo cáo bài chính với cùng code cuối. Điểm bonus tham khảo do bộ eval tính, không thay thế việc giảng viên chấm rubric và các yêu cầu nộp bài.

## 4. So sánh hai lần chạy

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---|---|
| Điểm tổng | 89.09/100, chấm đủ 22/22 | 93.18/100, chấm đủ 22/22 |
| Điểm case đã chọn H7 | 35/100 | 100/100 |
| Số model calls của agent có usage | 48 | 49 |
| Tổng token agent báo về | 42,643 | 53,866 |
| Tổng token judge báo về | 36,085 | 38,105 |
| Tổng token agent + judge báo về | 78,728 | 91,971 |
| Event kiểm tra thiếu nguồn | 0 | 1, trong A7 |
| Chi phí tiền | API không cung cấp trong báo cáo | API không cung cấp trong báo cáo |

Hai file có khối `config` giống nhau: provider và judge_provider đều là `gemini`, model và judge_model đều là `gemini-3.1-flash-lite`, max_steps=8, dataset=core. Cả hai dùng cùng fixtures; agent không truy cập `expected` của case.

Điểm tổng tăng 4.09 điểm; token được báo về tăng 13,243 (khoảng 16.82%). Lượt sau có thêm 1 model call được ghi nhận. Prompt dài hơn và các lựa chọn công cụ/câu trả lời khác nhau đều có thể góp phần thay đổi lượng token; chưa có dữ liệu để quy đổi chính xác thành tiền.

| Case | Trước | Sau | Nhận xét từ trace |
|---|---:|---:|---|
| H7 | 35 | 100 | Đã báo Cloudflare chưa xác minh được khi timeout, vẫn báo cáo GitHub và dẫn nguồn. |
| E3 | 70 | 100 | Lượt sau dùng `get_status` không lọc component rồi đọc incident Spectrum; lượt trước tìm chuỗi `Cloudflare Spectrum` trả rỗng. |
| A1 | 95 | 100 | Lượt sau đọc chi tiết incident của cả hai nhà cung cấp. |
| E1 | 100 | 90 | Judge trừ factuality; cần đối chiếu nhận xét với dữ liệu thật, xem mục giới hạn bên dưới. |
| H1 | 60 | 60 | Chỉ đọc hai incident ban đầu trong cùng step; chưa theo liên kết để đọc incident gộp, thiếu bước điều tra tiếp theo. |
| H2 | 50 | 50 | Đọc incident lịch sử nhưng chưa gọi `get_status` để kiểm tra trạng thái theo snapshot. |
| H6 | 50 | 50 | Đã theo liên kết đọc incident gộp nhưng chưa gọi `get_status`; cần nêu rõ giới hạn nội dung bị cắt. |

- Lỗi đã cải thiện trong lượt đo: H7 không còn bịa Cloudflare operational theo yêu cầu người dùng. Đây là thay đổi chính được chọn và có bằng chứng trước/sau.
- Kiểm tra nguồn đã được thực thi: ở A7, step 3 có event `validation_missing_source` với URL Cloudflare đã quan sát. Agent được yêu cầu bổ sung nguồn trong giới hạn bước và cuối cùng hoàn thành. Test offline cũng kiểm tra trường hợp hết budget và trường hợp tool đọc incident thất bại.
- Lỗi còn lại hoặc mới xuất hiện được ghi ở bảng trên. Với H1, bước cần bổ sung là model đọc liên kết incident rồi yêu cầu tool tiếp theo; vẫn phải xử lý đầy đủ mọi call trong cùng response theo contract, ghi step đúng số lần gọi model.
- Demo trace nhiều bước có thể dùng E3 trong `eval_after.json`: step 1 gọi `get_status` Cloudflare; step 2 gọi `get_incident_details` bằng ID lấy từ kết quả; step 3 dừng `stop` và trả lời. Demo lỗi có thể dùng H7 trước/sau và H1 còn thiếu bước theo liên kết.

## 5. Giới hạn

- Judge là AI nên điểm và nhận xét có thể sai. Ví dụ H1 được judge cho điểm thô 100 nhưng bị kiểm tra code giới hạn còn 60 vì thiếu bước dùng tool tiếp theo; cần đọc cả trace và `grade.mechanical`.
- E1 sau cải tiến bị judge nhận xét ID có vẻ bịa hoặc nhầm. Đối chiếu trace, ba ID `h02n9572mx9y`, `xr3myzj7ms51`, `t89g2q1800fr` trong answer đều có trong kết quả tool, nên nhận xét này chưa được chứng minh ở phần ID. Tuy nhiên, answer còn dùng ngày `updated_at` như ngày giải quyết, trong khi hai mốc không nhất thiết giống nhau. Giữ nguyên điểm judge trong báo cáo và ghi nhận giới hạn này, không sửa tay điểm.
- Snapshot bài chính là dữ liệu lưu ngày 09/11/2026, không đại diện trạng thái dịch vụ khi chạy bài ngoài đời.
- Kết quả trước cải tiến được hoàn tất bằng chạy tiếp các case unscored do lỗi API, cùng cấu hình: Gemini `gemini-3.1-flash-lite` cho agent và judge, max_steps=8, dataset=core. Giữ nguyên 17 case đã chấm; A2/A3/A6/A7 chạy lại, A5 chỉ chấm lại câu trả lời đã có. Dùng `run_evals_slow.py` và `resume_evals.py` để điều tiết tốc độ và thử lại có giới hạn; không sửa dataset, fixtures hoặc bộ chấm.
- Thống kê token/model calls ở bảng được cộng từ các response có usage trong báo cáo cuối. Không bao gồm toàn bộ lời gọi thất bại hoặc các lần thử trước đó bị thay thế khi chạy tiếp, nên không dùng để khẳng định tổng chi phí thực tế.
- Một lượt đầy đủ cho mỗi phiên bản chưa chứng minh độ ổn định; việc dùng cùng model cho agent và judge có thể gây thiên lệch. Mức tăng 4.09 điểm là kết quả quan sát được ở hai báo cáo này, chưa chứng minh mọi thay đổi điểm đều do phần cải tiến gây ra.
