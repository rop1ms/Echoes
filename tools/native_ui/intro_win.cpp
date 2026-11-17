// Заставка ECHOES в своём потоке и своём окне (intro_anim.start_native).
//
// Раньше заставка рисовалась в потоке интерфейса: пока плеер загружался, её кадры стояли. Здесь отдельный
// поток создаёт своё окно Win32 (без рамки, поверх окна плеера), рисует кадры QPainter'ом в картинку
// (DIB) и выводит её в ритме экрана (DwmFlush) — ни поток интерфейса, ни GIL Python ей не нужны. Поэтому
// пока идёт заставка, плеер спокойно загружает всё заранее (страницы, первые кадры, GL), а заставка не
// дёргается. Сюжет монохромный, без акцентного цвета (тот же, что intro_anim.paint): из центра вырастает
// тонкая белая линия, из-за неё буква за буквой поднимается ECHOES, по надписи пробегает блик; пока плеер
// не готов, по линии бежит блик загрузки. Готов (eui_intro_ready) и сюжет досмотрен — заставка
// растворяется, а плеер в этот миг собирает сцену (ph_intro; момент — eui_intro_fading). Клик — не ждать.
#include <windows.h>
#include <dwmapi.h>
#include <QtGui/QColor>
#include <QtGui/QFont>
#include <QtGui/QFontMetricsF>
#include <QtGui/QImage>
#include <QtGui/QLinearGradient>
#include <QtGui/QPainter>
#include <QtGui/QPainterPath>
#include <QtGui/QRadialGradient>
#include <QtCore/QString>
#include <atomic>
#include <chrono>
#include <cmath>
#include <mutex>
#include <thread>

#pragma comment(lib, "dwmapi.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "user32.lib")

#define EUI_API extern "C" __declspec(dllexport)

namespace {

constexpr double T_LINE = 0.0, LINE_GROW = 0.5, T_TEXT = 0.22, LETTER_STEP = 0.06, LETTER_RISE = 0.5;
constexpr double T_SWEEP = 0.95, SWEEP = 0.5, T_SEQ = 1.45, FADE = 0.45, LINE_W = 260.0;

double clamp01(double x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
double out_cubic(double x) { x = clamp01(x); return 1 - (1 - x) * (1 - x) * (1 - x); }
double out_back(double x, double s) { x = clamp01(x) - 1; return 1 + (s + 1) * x * x * x + s * x * x; }
double in_out(double x) { x = clamp01(x); return x < 0.5 ? 4 * x * x * x : 1 - std::pow(-2 * x + 2, 3) / 2; }

struct Intro {
    std::thread th;
    std::atomic<bool> alive{false}, ready{false}, skip{false}, fading{false};
    std::atomic<HWND> owner{nullptr};
    std::atomic<int> frames{0};
    std::mutex mu;
    RECT rect{};
    double dpr = 1.0;
    QColor acc{255, 219, 26};
    QString text = QStringLiteral("ECHOES"), family;
    HWND hwnd = nullptr;
    double fade_t0 = -1;
    double ready_t = -1;

    static LRESULT CALLBACK proc(HWND h, UINT m, WPARAM w, LPARAM l) {
        auto *self = reinterpret_cast<Intro *>(GetWindowLongPtrW(h, GWLP_USERDATA));
        if (m == WM_LBUTTONDOWN && self) { self->skip = true; return 0; }
        if (m == WM_MOUSEACTIVATE) return MA_NOACTIVATE;
        if (m == WM_ERASEBKGND) return 1;
        return DefWindowProcW(h, m, w, l);
    }

    void run();
    void draw(QPainter &p, double W, double H, double t, double out);
};

Intro *g_intro = nullptr;

void Intro::draw(QPainter &p, double W, double H, double t, double out) {
    p.fillRect(QRectF(0, 0, W, H), Qt::black);
    const double alpha = 1.0 - out;
    if (alpha <= 0.01) return;
    p.setOpacity(alpha);
    const double cx = W / 2, cy = H / 2, line_y = cy + 30, lift = -10 * out;
    const double hold = std::min(t, T_SEQ) < T_SEQ ? 0.0 : (ready ? 0.0 : t - T_SEQ);
    // линия: из центра в стороны, к краям гаснет
    const double k = out_cubic((t - T_LINE) / LINE_GROW);
    if (k > 0) {
        const double w = LINE_W * k;
        QLinearGradient g(QPointF(cx - w / 2, 0), QPointF(cx + w / 2, 0));
        g.setColorAt(0, QColor(255, 255, 255, 0)); g.setColorAt(0.5, QColor(255, 255, 255, 200));
        g.setColorAt(1, QColor(255, 255, 255, 0));
        p.fillRect(QRectF(cx - w / 2, line_y + lift, w, 1.5), g);
        if (k < 1) {                                              // светящиеся кончики, пока растёт
            for (int sx : {-1, 1}) {
                QPointF c(cx + sx * w / 2, line_y + lift + 0.75);
                QRadialGradient rg(c, 10);
                rg.setColorAt(0, QColor(255, 255, 255, int(180 * (1 - k))));
                rg.setColorAt(1, QColor(255, 255, 255, 0));
                p.setPen(Qt::NoPen); p.setBrush(rg); p.drawEllipse(c, 10, 10);
            }
        }
        if (t > T_SEQ && out <= 0) {                              // плеер ещё грузится — по линии бежит блик
            const double ph = std::fmod((t - T_SEQ) / 1.2, 1.0);
            const double bx = cx - w / 2 + (w + 80) * ph - 40;
            QLinearGradient sg(QPointF(bx - 40, 0), QPointF(bx + 40, 0));
            sg.setColorAt(0, QColor(255, 255, 255, 0)); sg.setColorAt(0.5, QColor(255, 255, 255, 255));
            sg.setColorAt(1, QColor(255, 255, 255, 0));
            p.save(); p.setClipRect(QRectF(cx - w / 2, line_y + lift - 1, w, 4));
            p.fillRect(QRectF(bx - 40, line_y + lift - 0.5, 80, 2.5), sg);
            p.restore();
        }
    }
    (void)hold;
    // надпись: буквы поднимаются из-за линии, разрядка сходится
    QFont f(family.isEmpty() ? QStringLiteral("Segoe UI") : family);
    f.setPixelSize(64);
    f.setWeight(QFont::Black);
    QFontMetricsF fm(f);
    const double spread = 1 - out_cubic((t - T_TEXT) / 0.8);
    const double gap = 4 + 22 * spread;
    QList<double> widths;
    double total = 0;
    for (QChar ch : text) { widths.append(fm.horizontalAdvance(ch)); total += widths.last(); }
    total += gap * (text.size() - 1);
    const double base_y = line_y - 14 + lift;
    QPainterPath path;
    p.save();
    p.setClipRect(QRectF(0, 0, W, line_y + lift - 2));            // из-за линии: ниже неё букв не видно
    p.setFont(f);
    double x = cx - total / 2;
    for (int j = 0; j < text.size(); ++j) {
        const double kj = out_cubic((t - T_TEXT - j * LETTER_STEP) / LETTER_RISE);
        if (kj > 0) {
            p.setPen(QColor(228, 228, 228, int(255 * std::min(1.0, kj * 1.2))));   // чуть серее — блик виден
            p.drawText(QPointF(x, base_y + 70 * (1 - kj)), QString(text[j]));
        }
        path.addText(QPointF(x, base_y), f, QString(text[j]));
        x += widths[j] + gap;
    }
    p.restore();
    const double sw = (t - T_SWEEP) / SWEEP;
    if (sw > 0 && sw < 1) {                                       // блик пробегает по надписи
        const double c = cx - total / 2 - 80 + (total + 160) * sw;
        QLinearGradient band(QPointF(c - 70, 0), QPointF(c + 70, 0));
        band.setColorAt(0, QColor(255, 255, 255, 0)); band.setColorAt(0.5, QColor(255, 255, 255, 230));
        band.setColorAt(1, QColor(255, 255, 255, 0));
        p.save(); p.setClipPath(path);
        p.fillRect(QRectF(cx - total / 2 - 10, base_y - fm.ascent() - 10, total + 20, fm.height() + 20), band);
        p.restore();
        const QPointF hc(c, base_y - fm.ascent() / 2);
        QRadialGradient halo(hc, 90);
        halo.setColorAt(0, QColor(255, 255, 255, int(26 * std::sin(3.14159265 * sw))));
        halo.setColorAt(1, QColor(255, 255, 255, 0));
        p.setPen(Qt::NoPen); p.setBrush(halo); p.drawEllipse(hc, 90, 90);
    }
}

void Intro::run() {
    HINSTANCE inst = GetModuleHandleW(nullptr);
    WNDCLASSW wc{};
    wc.lpfnWndProc = &Intro::proc;
    wc.hInstance = inst;
    wc.lpszClassName = L"EchoesIntroWindow";
    wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    RegisterClassW(&wc);
    RECT r;
    { std::lock_guard<std::mutex> g(mu); r = rect; }
    hwnd = CreateWindowExW(WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE, wc.lpszClassName, L"ECHOES",
                           WS_POPUP, r.left, r.top, r.right - r.left, r.bottom - r.top, nullptr, nullptr, inst, nullptr);
    if (!hwnd) { alive = false; return; }
    SetWindowLongPtrW(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(this));
    SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA);
    ShowWindow(hwnd, SW_SHOWNOACTIVATE);
    HDC wdc = GetDC(hwnd);
    HDC mdc = CreateCompatibleDC(wdc);
    HBITMAP bmp = nullptr;
    void *bits = nullptr;
    int bw = 0, bh = 0;
    auto start = std::chrono::steady_clock::now();
    for (;;) {
        MSG msg;
        while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE)) { TranslateMessage(&msg); DispatchMessageW(&msg); }
        double t = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
        HWND own = owner.load();
        if (own && IsWindow(own)) {                               // окно плеера уже есть — встать ровно поверх него
            // Только читаем, где окно плеера. Владельцем его НЕ делаем: у «владеемого» окна смена порядка
            // синхронизируется с потоком владельца, и пока поток интерфейса загружает плеер, заставка стояла.
            RECT cr; POINT tl{0, 0};
            if (!IsIconic(own) && GetClientRect(own, &cr) && ClientToScreen(own, &tl) && cr.right > 10 && cr.bottom > 10) {
                RECT want{tl.x, tl.y, tl.x + cr.right, tl.y + cr.bottom};
                if (want.left != r.left || want.top != r.top || want.right != r.right || want.bottom != r.bottom) {
                    r = want;
                    SetWindowPos(hwnd, nullptr, r.left, r.top, r.right - r.left, r.bottom - r.top, SWP_NOACTIVATE | SWP_NOZORDER);
                }
                UINT dpi = GetDpiForWindow(own);
                if (dpi) dpr = dpi / 96.0;
            }
        }
        if (ready && ready_t < 0) ready_t = t;
        double seq_end = skip ? std::min(T_SEQ, t) : T_SEQ;
        if (fade_t0 < 0 && ready && t >= seq_end) { fade_t0 = t; fading = true; }
        double out = fade_t0 < 0 ? 0.0 : in_out((t - fade_t0) / FADE);
        const int W = std::max(1, int(r.right - r.left)), H = std::max(1, int(r.bottom - r.top));
        if (W != bw || H != bh || !bmp) {
            if (bmp) DeleteObject(bmp);
            BITMAPINFO bi{};
            bi.bmiHeader.biSize = sizeof bi.bmiHeader;
            bi.bmiHeader.biWidth = W;
            bi.bmiHeader.biHeight = -H;                           // сверху вниз, как QImage
            bi.bmiHeader.biPlanes = 1;
            bi.bmiHeader.biBitCount = 32;
            bi.bmiHeader.biCompression = BI_RGB;
            bmp = CreateDIBSection(mdc, &bi, DIB_RGB_COLORS, &bits, nullptr, 0);
            SelectObject(mdc, bmp);
            bw = W; bh = H;
        }
        if (bits) {
            QImage img(static_cast<uchar *>(bits), W, H, W * 4, QImage::Format_RGB32);
            QPainter p(&img);
            p.setRenderHint(QPainter::Antialiasing);
            p.setRenderHint(QPainter::TextAntialiasing);
            p.scale(dpr, dpr);
            draw(p, W / dpr, H / dpr, t, out);
            p.end();
            GdiFlush();
            BitBlt(wdc, 0, 0, W, H, mdc, 0, 0, SRCCOPY);
            SetLayeredWindowAttributes(hwnd, 0, BYTE(255 * (1.0 - out)), LWA_ALPHA);
            ++frames;
        }
        if (fade_t0 >= 0 && t - fade_t0 >= FADE) break;
        if (FAILED(DwmFlush())) Sleep(8);                         // кадр — в ритме экрана
    }
    if (bmp) DeleteObject(bmp);
    DeleteDC(mdc);
    ReleaseDC(hwnd, wdc);
    DestroyWindow(hwnd);
    hwnd = nullptr;
    alive = false;
}

}  // namespace

// Запустить заставку (один раз): прямоугольник на экране (пиксели устройства), dpr, цвет (не используется —
// заставка монохромная), надпись, шрифт.
EUI_API int eui_intro_start(int x, int y, int w, int h, double dpr, int r, int g, int b, const wchar_t *text,
                            const wchar_t *family) {
    if (g_intro) return 0;
    g_intro = new Intro;
    g_intro->rect = RECT{x, y, x + w, y + h};
    g_intro->dpr = dpr > 0 ? dpr : 1.0;
    g_intro->acc = QColor(r, g, b);
    if (text && *text) g_intro->text = QString::fromWCharArray(text);
    if (family) g_intro->family = QString::fromWCharArray(family);
    g_intro->alive = true;
    g_intro->th = std::thread([] { g_intro->run(); });
    g_intro->th.detach();
    return 1;
}

// окно плеера показано — заставка встаёт ровно поверх его клиентской области и держится над ним
EUI_API void eui_intro_follow(intptr_t hwnd) { if (g_intro) g_intro->owner = reinterpret_cast<HWND>(hwnd); }
// плеер всё загрузил — досмотреть сюжет и раствориться
EUI_API void eui_intro_ready() { if (g_intro) g_intro->ready = true; }
EUI_API int eui_intro_alive() { return g_intro && g_intro->alive ? 1 : 0; }
// заставка начала растворяться (или уже закрылась) — в этот миг плеер собирает сцену (ph_intro)
EUI_API int eui_intro_fading() { return !g_intro || g_intro->fading || !g_intro->alive ? 1 : 0; }
// сколько кадров показано (проверка: заставка идёт, пока поток интерфейса занят)
EUI_API int eui_intro_frames() { return g_intro ? g_intro->frames.load() : 0; }
