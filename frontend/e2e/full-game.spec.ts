import { devices, expect, test, type Browser, type Page } from "@playwright/test";

// AC9: 4 người chơi thật trên trình duyệt (1 người dùng điện thoại) — Home → sảnh → phòng → sẵn sàng →
// bàn chơi → chơi trọn ván bằng cách bấm lá bài → bảng kết quả.

async function newPlayer(browser: Browser, mobile = false): Promise<Page> {
  const context = await browser.newContext(mobile ? { ...devices["iPhone 13"] } : { viewport: { width: 1280, height: 800 } });
  return context.newPage();
}

async function enterNickname(page: Page, nickname: string, path = "/") {
  await page.goto(path);
  await page.getByLabel("Tên hiển thị của bạn").fill(nickname);
  await page.getByRole("button", { name: "Vào chơi" }).click();
}

/** Bot bấm giao diện: mở vòng thì đánh 3♣ (nếu bắt buộc) hoặc lá nhỏ nhất; đang theo thì bỏ lượt. */
async function playUntilResult(page: Page) {
  const result = page.getByRole("dialog", { name: /Ván kết thúc|Tới trắng|Đút mù/ });
  for (let i = 0; i < 400; i++) {
    if (await result.isVisible()) return;
    const myTurn = page.getByText("LƯỢT CỦA BẠN");
    if (await myTurn.isVisible()) {
      const pass = page.getByRole("button", { name: "Bỏ lượt" });
      if (await pass.isEnabled()) {
        await pass.click();
      } else {
        const mustThreeClubs = await page.getByText("(phải có 3♣)").isVisible();
        const card = mustThreeClubs
          ? page.locator(".my-hand").getByRole("button", { name: "3♣", exact: true })
          : page.locator(".my-hand button.card").first();
        await card.click({ position: { x: 8, y: 12 } });
        await page.getByRole("button", { name: /^Đánh/ }).click();
      }
      await page.waitForTimeout(250); // tốc độ người thật (server giới hạn 10 lệnh/giây)
    } else {
      await page.waitForTimeout(150);
    }
  }
  throw new Error("Ván chưa kết thúc sau 400 vòng lặp");
}

test("4 người chơi trọn một ván trên trình duyệt, có người dùng điện thoại", async ({ browser }, testInfo) => {
  const shot = (page: Page, name: string) => page.screenshot({ path: testInfo.outputPath(`${name}.png`), fullPage: true });
  const names = ["Lan", "Huy", "Minh", "Đức"];
  const pages = [await newPlayer(browser), await newPlayer(browser), await newPlayer(browser), await newPlayer(browser, true)];

  // Chủ phòng tạo phòng
  await enterNickname(pages[0]!, names[0]!);
  await expect(pages[0]!).toHaveURL(/\/lobby$/);
  await pages[0]!.getByRole("button", { name: /Đổi tên/ }).click();
  await pages[0]!.getByLabel("Tên hiển thị mới").fill("Lan Mới");
  await pages[0]!.getByRole("button", { name: "Lưu", exact: true }).click();
  await expect(pages[0]!.getByText("Lan Mới", { exact: true })).toBeVisible();
  await pages[0]!.getByRole("button", { name: "Tạo phòng mới" }).click();
  await expect(pages[0]!).toHaveURL(/\/r\/[A-Z2-9]{6}$/);
  const code = pages[0]!.url().split("/r/")[1]!;
  await expect(pages[0]!.getByRole("heading", { name: `Phòng ${code}` })).toBeVisible();

  // 3 người vào bằng link mời
  for (let i = 1; i < 4; i++) {
    await enterNickname(pages[i]!, names[i]!, `/?next=/r/${code}`);
    await expect(pages[i]!).toHaveURL(new RegExp(`/r/${code}$`));
    await expect(pages[i]!.getByText(`${names[i]} (bạn)`)).toBeVisible();
  }
  await expect(pages[0]!.getByText("4/4 người", { exact: false })).toBeVisible();
  await shot(pages[0]!, "1-phong-cho");

  // Xem luật trên điện thoại bằng popup, vẫn giữ phòng và kết nối.
  await pages[3]!.getByRole("button", { name: "Luật v1", exact: true }).click();
  const rulesDialog = pages[3]!.getByRole("dialog", { name: "Luật đang áp dụng" });
  await expect(rulesDialog.getByText(/Phiên bản/)).toBeVisible();
  await rulesDialog.getByRole("button", { name: "Đóng", exact: true }).click();
  await expect(pages[3]!).toHaveURL(new RegExp(`/r/${code}$`));

  // Cả 4 sẵn sàng → server chia bài
  for (const page of pages) await page.getByRole("button", { name: "Sẵn sàng", exact: true }).click();
  for (const page of pages) {
    await expect(page.getByRole("region", { name: "Bàn chơi" })).toBeVisible();
    await expect(page.locator(".my-hand button.card")).toHaveCount(13);
  }

  await pages[0]!.locator(".my-hand button.card").nth(2).click({ position: { x: 8, y: 12 } }); // chọn thử 1 lá để thấy hiệu ứng
  await shot(pages[0]!, "2-ban-choi-may-tinh");
  await shot(pages[3]!, "3-ban-choi-dien-thoai");
  await pages[0]!.locator(".my-hand button.card").nth(2).click({ position: { x: 8, y: 12 } });

  // Điện thoại: không bị tràn ngang, nút thao tác nằm trong màn hình
  const phone = pages[3]!;
  const overflow = await phone.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await expect(phone.getByRole("button", { name: /^Đánh/ })).toBeInViewport();

  // Gửi chữ tự do từ điện thoại, nhận trên máy tính và ngược lại với câu chat mới.
  await phone.getByRole("button", { name: "💬 Chat", exact: true }).click();
  const compose = phone.getByRole("dialog", { name: "Chat", exact: true });
  await compose.getByRole("textbox", { name: "Tin nhắn" }).fill("Kiểm tra chat mới");
  await compose.getByRole("button", { name: "Gửi", exact: true }).click();
  await expect(pages[0]!.locator(".chat-bubble").filter({ hasText: "Kiểm tra chat mới" })).toBeVisible();
  await pages[0]!.getByRole("button", { name: "💬 Chat", exact: true }).click();
  await pages[0]!.getByRole("dialog", { name: "Chat", exact: true }).getByRole("button", { name: "Xin cây 3 bích", exact: true }).click();
  await expect(phone.locator(".chat-bubble").filter({ hasText: "Xin cây 3 bích" })).toBeVisible();

  // Kéo lá đầu về cuối trên máy tính, rồi trả về thứ tự tự xếp để bot chơi.
  const first = pages[0]!.locator(".my-hand button.card").first();
  const label = await first.textContent();
  const box = (await first.boundingBox())!;
  const lastBox = (await pages[0]!.locator(".my-hand button.card").last().boundingBox())!;
  await pages[0]!.mouse.move(box.x + 8, box.y + 12);
  await pages[0]!.mouse.down();
  await pages[0]!.mouse.move(lastBox.x + lastBox.width - 2, lastBox.y + 12, { steps: 8 });
  await pages[0]!.mouse.up();
  await expect(pages[0]!.locator(".my-hand button.card").last()).toHaveText(label!);
  await pages[0]!.getByRole("button", { name: "Xếp theo chất", exact: true }).click();
  await pages[0]!.getByRole("button", { name: "Xếp theo số", exact: true }).click();

  // Bố cục xoay ngang và popup thông tin đều nằm trong màn hình điện thoại.
  await phone.setViewportSize({ width: 844, height: 390 });
  await expect(phone.getByRole("button", { name: /^Đánh/ })).toBeInViewport();
  await phone.getByRole("button", { name: /Thông tin/ }).click();
  const info = phone.getByRole("dialog", { name: "Thông tin", exact: true });
  await expect(info).toBeInViewport();
  await info.getByRole("button", { name: "Đóng", exact: true }).click();
  expect(await phone.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
  await shot(phone, "3b-dien-thoai-ngang");
  await phone.setViewportSize({ width: 390, height: 844 });

  // Chơi trọn ván
  await Promise.all(pages.map(playUntilResult));
  await shot(pages[0]!, "4-ket-qua");
  for (const page of pages) {
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText(/Tổng điểm 4 người: 0/)).toBeVisible();
    await expect(dialog.getByRole("row")).toHaveCount(5); // tiêu đề + 4 người
  }

  // Ván tiếp theo: bảng điểm phiên đã cộng điểm, mọi người bấm sẵn sàng lại
  for (const page of pages) await page.getByRole("button", { name: "Sẵn sàng ván tiếp" }).click();
  await expect(pages[0]!.getByText(/Phiên 1 · 1 ván/)).toBeVisible();
  for (const page of pages) await expect(page.locator(".my-hand button.card")).toHaveCount(13);

  // Lịch sử phiên ghi nhận ván đã chơi
  await pages[1]!.getByRole("link", { name: "Lịch sử" }).click();
  await expect(pages[1]!.getByRole("heading", { name: /Phiên 1 · phòng/ })).toBeVisible();
  await expect(pages[1]!.getByRole("link", { name: "Xem lại" })).toBeVisible();
  await shot(pages[1]!, "5-lich-su");
});
