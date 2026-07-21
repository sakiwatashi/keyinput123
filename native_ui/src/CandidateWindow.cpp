//
//    Copyright (C) 2013 - 2020 Hong Jen Yee (PCMan) <pcman.tw@gmail.com>
//
//    This library is free software; you can redistribute it and/or
//    modify it under the terms of the GNU Library General Public
//    License as published by the Free Software Foundation; either
//    version 2 of the License, or (at your option) any later version.
//
//    This library is distributed in the hope that it will be useful,
//    but WITHOUT ANY WARRANTY; without even the implied warranty of
//    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
//    Library General Public License for more details.
//
//    You should have received a copy of the GNU Library General Public
//    License along with this library; if not, write to the
//    Free Software Foundation, Inc., 51 Franklin St, Fifth Floor,
//    Boston, MA  02110-1301, USA.
//

#include "CandidateWindow.h"
#include "DrawUtils.h"
#include "TextService.h"
#include "EditSession.h"

#include <algorithm>
#include <cassert>

#include <tchar.h>
#include <windows.h>

using namespace std;

namespace Ime {

namespace {

const COLORREF kBackground = RGB(250, 249, 247);
const COLORREF kBorder = RGB(218, 216, 211);
const COLORREF kText = RGB(38, 37, 35);
const COLORREF kLabel = RGB(111, 105, 96);
const COLORREF kSelectedBackground = RGB(231, 235, 248);
const COLORREF kSelectedLabel = RGB(72, 83, 145);

int scaledPixel(int value) {
    HDC screen = ::GetDC(NULL);
    int dpi = screen ? ::GetDeviceCaps(screen, LOGPIXELSX) : 96;
    if(screen)
        ::ReleaseDC(NULL, screen);
    return ::MulDiv(value, dpi, 96);
}

void candidateGrid(int itemCount, int maxColumns, int& rows, int& columns) {
    if(itemCount <= 0) {
        rows = 0;
        columns = 0;
        return;
    }

    // Smart Priority Bopomofo uses two columns of five. Fill the left column
    // (1-5) before the right column (6-0), matching Microsoft Bopomofo instead
    // of the original row-major 1/2, 3/4 layout.
    if(maxColumns == 2 && itemCount <= 10) {
        rows = min(5, itemCount);
        columns = (itemCount + rows - 1) / rows;
        return;
    }

    columns = min(maxColumns, itemCount);
    rows = (itemCount + columns - 1) / columns;
}

void fillRoundRect(HDC hdc, const RECT& rect, int radius, COLORREF color) {
    HBRUSH brush = ::CreateSolidBrush(color);
    HPEN pen = ::CreatePen(PS_NULL, 0, color);
    HGDIOBJ oldBrush = ::SelectObject(hdc, brush);
    HGDIOBJ oldPen = ::SelectObject(hdc, pen);
    ::RoundRect(hdc, rect.left, rect.top, rect.right, rect.bottom, radius, radius);
    ::SelectObject(hdc, oldPen);
    ::SelectObject(hdc, oldBrush);
    ::DeleteObject(pen);
    ::DeleteObject(brush);
}

} // namespace

CandidateWindow::CandidateWindow(TextService* service, EditSession* session):
    ImeWindow(service),
    shown_(false),
    candPerRow_(1),
    textWidth_(0),
    itemHeight_(0),
    currentSel_(0),
    hasResult_(false),
    useCursor_(true),
    selKeyWidth_(0) {

    // A restrained Japanese-inspired surface: generous whitespace, a warm
    // paper background, subtle indigo selection, and no legacy 3D chrome.
    margin_ = scaledPixel(10);
    rowSpacing_ = scaledPixel(4);
    colSpacing_ = scaledPixel(8);

    HWND parent = service->compositionWindow(session);
    create(parent, WS_POPUP|WS_CLIPCHILDREN,
           WS_EX_TOOLWINDOW|WS_EX_TOPMOST|WS_EX_NOACTIVATE);
}

CandidateWindow::~CandidateWindow(void) {
}

// ITfUIElement
STDMETHODIMP CandidateWindow::GetDescription(BSTR *pbstrDescription) {
    if (!pbstrDescription)
        return E_INVALIDARG;
    *pbstrDescription = SysAllocString(L"Candidate window~");
    return S_OK;
}

// {BD7CCC94-57CD-41D3-A789-AF47890CEB29}
STDMETHODIMP CandidateWindow::GetGUID(GUID *pguid) {
    if (!pguid)
        return E_INVALIDARG;
    *pguid = { 0xbd7ccc94, 0x57cd, 0x41d3, { 0xa7, 0x89, 0xaf, 0x47, 0x89, 0xc, 0xeb, 0x29 } };
    return S_OK;
}

STDMETHODIMP CandidateWindow::Show(BOOL bShow) {
    shown_ = bShow;
    if (shown_)
        show();
    else
        hide();
    return S_OK;
}

STDMETHODIMP CandidateWindow::IsShown(BOOL *pbShow) {
    if (!pbShow)
        return E_INVALIDARG;
    *pbShow = shown_;
    return S_OK;
}

// ITfCandidateListUIElement
STDMETHODIMP CandidateWindow::GetUpdatedFlags(DWORD *pdwFlags) {
    if (!pdwFlags)
        return E_INVALIDARG;
    /// XXX update all!!!
    *pdwFlags = TF_CLUIE_DOCUMENTMGR | TF_CLUIE_COUNT | TF_CLUIE_SELECTION | TF_CLUIE_STRING | TF_CLUIE_PAGEINDEX | TF_CLUIE_CURRENTPAGE;
    return S_OK;
}

STDMETHODIMP CandidateWindow::GetDocumentMgr(ITfDocumentMgr **ppdim) {
    if (!textService_)
        return E_FAIL;
    return textService_->currentContext()->GetDocumentMgr(ppdim);
}

STDMETHODIMP CandidateWindow::GetCount(UINT *puCount) {
    if (!puCount)
        return E_INVALIDARG;
    *puCount = std::min<UINT>(10, items_.size());
    return S_OK;
}

STDMETHODIMP CandidateWindow::GetSelection(UINT *puIndex) {
    assert(currentSel_ >= 0);
    if (!puIndex)
        return E_INVALIDARG;
    *puIndex = static_cast<UINT>(currentSel_);
    return S_OK;
}

STDMETHODIMP CandidateWindow::GetString(UINT uIndex, BSTR *pbstr) {
    if (!pbstr)
        return E_INVALIDARG;
    if (uIndex >= items_.size())
        return E_INVALIDARG;
    *pbstr = SysAllocString(items_[uIndex].c_str());
    return S_OK;
}

STDMETHODIMP CandidateWindow::GetPageIndex(UINT *puIndex, UINT uSize, UINT *puPageCnt) {
    /// XXX Always return the same single page index.
    if (!puPageCnt)
        return E_INVALIDARG;
    *puPageCnt = 1;
    if (puIndex) {
        if (uSize < *puPageCnt) {
            return E_INVALIDARG;
        }
        puIndex[0] = 0;
    }
    return S_OK;
}

STDMETHODIMP CandidateWindow::SetPageIndex(UINT *puIndex, UINT uPageCnt) {
    /// XXX Do not let app set page indices.
    if (!puIndex)
        return E_INVALIDARG;
    return S_OK;
}

STDMETHODIMP CandidateWindow::GetCurrentPage(UINT *puPage) {
    if (!puPage)
        return E_INVALIDARG;
    *puPage = 0;
    return S_OK;
}

LRESULT CandidateWindow::wndProc(UINT msg, WPARAM wp , LPARAM lp) {
    switch (msg) {
        case WM_PAINT:
            onPaint(wp, lp);
            break;
        case WM_ERASEBKGND:
            return TRUE;
            break;
        case WM_LBUTTONDOWN:
            onLButtonDown(wp, lp);
            break;
        case WM_MOUSEMOVE:
            onMouseMove(wp, lp);
            break;
        case WM_LBUTTONUP:
            onLButtonUp(wp, lp);
            break;
        case WM_MOUSEACTIVATE:
            return MA_NOACTIVATE;
        default:
            return Window::wndProc(msg, wp, lp);
    }
    return 0;
}

void CandidateWindow::onPaint(WPARAM wp, LPARAM lp) {
    PAINTSTRUCT ps;
    BeginPaint(hwnd_, &ps);
    RECT rc;
    GetClientRect(hwnd_,&rc);

    // Double-buffer the small popup to keep rapid candidate changes quiet and
    // flicker-free.
    HDC hDC = ::CreateCompatibleDC(ps.hdc);
    HBITMAP bitmap = ::CreateCompatibleBitmap(
        ps.hdc, rc.right - rc.left, rc.bottom - rc.top);
    HGDIOBJ oldBitmap = ::SelectObject(hDC, bitmap);
    HFONT oldFont = (HFONT)::SelectObject(hDC, font_);
    ::SetBkMode(hDC, TRANSPARENT);

    fillRoundRect(hDC, rc, scaledPixel(12), kBackground);
    HPEN borderPen = ::CreatePen(PS_SOLID, scaledPixel(1), kBorder);
    HGDIOBJ oldPen = ::SelectObject(hDC, borderPen);
    HGDIOBJ oldBrush = ::SelectObject(hDC, ::GetStockObject(NULL_BRUSH));
    ::RoundRect(hDC, rc.left, rc.top, rc.right - 1, rc.bottom - 1,
                scaledPixel(12), scaledPixel(12));
    ::SelectObject(hDC, oldBrush);
    ::SelectObject(hDC, oldPen);
    ::DeleteObject(borderPen);

    // paint items
    for(int i = 0, n = items_.size(); i < n; ++i) {
        RECT item;
        itemRect(i, item);
        paintItem(hDC, i, item.left, item.top);
    }
    ::BitBlt(ps.hdc, 0, 0, rc.right, rc.bottom, hDC, 0, 0, SRCCOPY);
    ::SelectObject(hDC, oldFont);
    ::SelectObject(hDC, oldBitmap);
    ::DeleteObject(bitmap);
    ::DeleteDC(hDC);
    EndPaint(hwnd_, &ps);
}

void CandidateWindow::recalculateSize() {
    if(items_.empty()) {
        resize(margin_ * 2, margin_ * 2);
    }

    HDC hDC = ::GetWindowDC(hwnd());
    int height = 0;
    int width = 0;
    selKeyWidth_ = 0;
    textWidth_ = 0;
    itemHeight_ = 0;

    HGDIOBJ oldFont = ::SelectObject(hDC, font_);
    vector<wstring>::const_iterator it;
    for(int i = 0, n = items_.size(); i < n; ++i) {
        SIZE selKeySize;
        int lineHeight = 0;
        // the selection key string
        wchar_t selKey[] = L"?";
        selKey[0] = selKeys_[i];
        ::GetTextExtentPoint32W(hDC, selKey, 1, &selKeySize);
        if(selKeySize.cx > selKeyWidth_)
            selKeyWidth_ = selKeySize.cx;

        // the candidate string
        SIZE candidateSize;
        wstring& item = items_.at(i);
        ::GetTextExtentPoint32W(hDC, item.c_str(), item.length(), &candidateSize);
        if(candidateSize.cx > textWidth_)
            textWidth_ = candidateSize.cx;
        int itemHeight = max(candidateSize.cy, selKeySize.cy);
        if(itemHeight > itemHeight_)
            itemHeight_ = itemHeight;
    }
    itemHeight_ += scaledPixel(12);
    selKeyWidth_ += scaledPixel(16);
    textWidth_ += scaledPixel(16);
    ::SelectObject(hDC, oldFont);
    ::ReleaseDC(hwnd(), hDC);

    int rowCount, columnCount;
    candidateGrid(static_cast<int>(items_.size()), candPerRow_, rowCount, columnCount);
    width = columnCount * (selKeyWidth_ + textWidth_);
    width += colSpacing_ * max(0, columnCount - 1);
    width += margin_ * 2;
    height = itemHeight_ * rowCount + rowSpacing_ * max(0, rowCount - 1);
    height += margin_ * 2;
    resize(width, height);
    HRGN region = ::CreateRoundRectRgn(
        0, 0, width + 1, height + 1, scaledPixel(12), scaledPixel(12));
    if(!::SetWindowRgn(hwnd(), region, TRUE))
        ::DeleteObject(region);
}

void CandidateWindow::setCandPerRow(int n) {
    if(n != candPerRow_) {
        candPerRow_ = n;
        recalculateSize();
    }
}

bool CandidateWindow::filterKeyEvent(KeyEvent& keyEvent) {
    // select item with arrow keys
    int oldSel = currentSel_;
    int itemCount = static_cast<int>(items_.size());
    int rowCount, columnCount;
    candidateGrid(itemCount, candPerRow_, rowCount, columnCount);
    int row = rowCount > 0 ? currentSel_ % rowCount : 0;
    int col = rowCount > 0 ? currentSel_ / rowCount : 0;
    switch(keyEvent.keyCode()) {
    case VK_UP:
        if(row > 0)
            --currentSel_;
        break;
    case VK_DOWN:
        if(row + 1 < rowCount && currentSel_ + 1 < itemCount)
            ++currentSel_;
        break;
    case VK_LEFT:
        if(col > 0)
            currentSel_ -= rowCount;
        break;
    case VK_RIGHT:
        if(col + 1 < columnCount && currentSel_ + rowCount < itemCount)
            currentSel_ += rowCount;
        break;
    case VK_RETURN:
        hasResult_ = true;
        return true;
    default:
        return false;
    }
    // if currently selected item is changed, redraw
    if(currentSel_ != oldSel) {
        // repaint the old and new items
        RECT rect;
        itemRect(oldSel, rect);
        ::InvalidateRect(hwnd_, &rect, TRUE);
        itemRect(currentSel_, rect);
        ::InvalidateRect(hwnd_, &rect, TRUE);
        return true;
    }
    return false;
}

void CandidateWindow::setCurrentSel(int sel) {
    if(sel >= items_.size())
        sel = 0;
    if (currentSel_ != sel) {
        currentSel_ = sel;
        if (isVisible())
            ::InvalidateRect(hwnd_, NULL, TRUE);
    }
}

void CandidateWindow::clear() {
    items_.clear();
    selKeys_.clear();
    currentSel_ = 0;
    hasResult_ = false;
}

void CandidateWindow::setUseCursor(bool use) {
    useCursor_ = use;
    if(isVisible())
        ::InvalidateRect(hwnd_, NULL, TRUE);
}

void CandidateWindow::paintItem(HDC hDC, int i,  int x, int y) {
    RECT cell = {
        x,
        y,
        x + selKeyWidth_ + textWidth_,
        y + itemHeight_
    };
    if(useCursor_ && i == currentSel_) {
        RECT selected = cell;
        ::InflateRect(&selected, -scaledPixel(2), -scaledPixel(1));
        fillRoundRect(hDC, selected, scaledPixel(8), kSelectedBackground);
    }

    wchar_t selKey[] = L"?";
    selKey[0] = selKeys_[i];
    int textY = y + scaledPixel(6);
    ::SetTextColor(hDC, i == currentSel_ ? kSelectedLabel : kLabel);
    ::TextOutW(hDC, x + scaledPixel(8), textY, selKey, 1);

    wstring& item = items_.at(i);
    ::SetTextColor(hDC, kText);
    ::TextOutW(hDC, x + selKeyWidth_, textY, item.c_str(), item.length());
}

void CandidateWindow::itemRect(int i, RECT& rect) {
    int row, col;
    int rowCount, columnCount;
    candidateGrid(static_cast<int>(items_.size()), candPerRow_, rowCount, columnCount);
    row = rowCount > 0 ? i % rowCount : 0;
    col = rowCount > 0 ? i / rowCount : 0;
    rect.left = margin_ + col * (selKeyWidth_ + textWidth_ + colSpacing_);
    rect.top = margin_ + row * (itemHeight_ + rowSpacing_);
    rect.right = rect.left + (selKeyWidth_ + textWidth_);
    rect.bottom = rect.top + itemHeight_;
}


} // namespace Ime
