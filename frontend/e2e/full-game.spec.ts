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
        await card.click();
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

  // Cả 4 sẵn sàng → server chia bài
  for (const page of pages) await page.getByRole("button", { name: "Sẵn sàng", exact: true }).click();
  for (const page of pages) {
    await expect(page.getByRole("region", { name: "Bàn chơi" })).toBeVisible();
    await expect(page.locator(".my-hand button.card")).toHaveCount(13);
  }

  await pages[0]!.locator(".my-hand button.card").nth(2).click(); // chọn thử 1 lá để thấy hiệu ứng
  await shot(pages[0]!, "2-ban-choi-may-tinh");
  await shot(pages[3]!, "3-ban-choi-dien-thoai");
  await pages[0]!.locator(".my-hand button.card").nth(2).click();

  // Điện thoại: không bị tràn ngang, nút thao tác nằm trong màn hình
  const phone = pages[3]!;
  const overflow = await phone.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await expect(phone.getByRole("button", { name: /^Đánh/ })).toBeInViewport();

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
