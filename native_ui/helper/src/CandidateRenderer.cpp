//
//    Derived from PIME's libIME2 CandidateWindow:
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

#include "CandidateRenderer.h"

#include <algorithm>

namespace SmartPriority {

namespace {

// A restrained Japanese-inspired surface: generous whitespace, a warm paper
// background, subtle indigo selection, and no legacy 3D chrome.
const COLORREF kBackground = RGB(250, 249, 247);
const COLORREF kBorder = RGB(218, 216, 211);
const COLORREF kText = RGB(38, 37, 35);
const COLORREF kLabel = RGB(111, 105, 96);
const COLORREF kSelectedBackground = RGB(231, 235, 248);
// Lighter than the selection so the two are never confused: this one only
// says what a click would pick, not what Enter will commit.
const COLORREF kHoverBackground = RGB(242, 243, 247);
const COLORREF kSelectedLabel = RGB(72, 83, 145);

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

void candidateGrid(int itemCount, int maxColumns, int& rows, int& columns) {
    if (itemCount <= 0) {
        rows = 0;
        columns = 0;
        return;
    }

    // Always use the vertical-first page for up to ten candidates: left column
    // 1-5 top-to-bottom, right column 6-0. Do not fall back to a row-major
    // "N per row" layout even if candPerRow is wrong.
    if (itemCount <= 10) {
        rows = std::min(5, itemCount);
        columns = (itemCount + rows - 1) / rows;
        return;
    }

    columns = std::min(std::max(1, maxColumns), itemCount);
    rows = (itemCount + columns - 1) / columns;
}

CandidateRenderer::CandidateRenderer():
    selection_(0),
    hover_(-1),
    candPerRow_(2),
    useCursor_(true),
    dpi_(96),
    selKeyWidth_(0),
    textWidth_(0),
    itemHeight_(0),
    margin_(0),
    rowSpacing_(0),
    colSpacing_(0) {
    setDpi(96);
}

CandidateRenderer::~CandidateRenderer() {
}

int CandidateRenderer::scaled(int value) const {
    return ::MulDiv(value, dpi_, 96);
}

void CandidateRenderer::setDpi(int dpi) {
    // The original in-process class read the primary screen DPI once, which
    // renders at the wrong size on a secondary monitor with a different scale.
    // The helper is per-monitor DPI aware and supplies the window's own value.
    dpi_ = dpi > 0 ? dpi : 96;
    margin_ = scaled(10);
    rowSpacing_ = scaled(4);
    colSpacing_ = scaled(8);
}

void CandidateRenderer::setCandidates(const std::vector<std::wstring>& items,
                                      const std::wstring& selectionKeys) {
    items_ = items;
    selectionKeys_ = selectionKeys;
    if (selection_ >= static_cast<int>(items_.size()))
        selection_ = 0;
    // A new page means the pointer is over a different candidate than before.
    hover_ = -1;
}

void CandidateRenderer::setSelection(int selection) {
    if (selection < 0 || selection >= static_cast<int>(items_.size()))
        selection = 0;
    selection_ = selection;
}

void CandidateRenderer::setHover(int hover) {
    if (hover < 0 || hover >= static_cast<int>(items_.size()))
        hover = -1;
    hover_ = hover;
}

void CandidateRenderer::setCandPerRow(int candPerRow) {
    candPerRow_ = candPerRow > 0 ? candPerRow : 1;
}

void CandidateRenderer::setUseCursor(bool useCursor) {
    useCursor_ = useCursor;
}

void CandidateRenderer::measureCells(HDC hdc) const {
    selKeyWidth_ = 0;
    textWidth_ = 0;
    itemHeight_ = 0;

    for (size_t i = 0; i < items_.size(); ++i) {
        SIZE selKeySize = {0, 0};
        if (i < selectionKeys_.size()) {
            wchar_t selKey[2] = {selectionKeys_[i], L'\0'};
            ::GetTextExtentPoint32W(hdc, selKey, 1, &selKeySize);
        }
        if (selKeySize.cx > selKeyWidth_)
            selKeyWidth_ = selKeySize.cx;

        SIZE candidateSize = {0, 0};
        const std::wstring& item = items_[i];
        ::GetTextExtentPoint32W(hdc, item.c_str(),
                                static_cast<int>(item.length()), &candidateSize);
        if (candidateSize.cx > textWidth_)
            textWidth_ = candidateSize.cx;

        long height = std::max(candidateSize.cy, selKeySize.cy);
        if (height > itemHeight_)
            itemHeight_ = static_cast<int>(height);
    }

    itemHeight_ += scaled(12);
    selKeyWidth_ += scaled(16);
    textWidth_ += scaled(16);
}

SIZE CandidateRenderer::measure(HDC hdc) const {
    SIZE size = {margin_ * 2, margin_ * 2};
    if (items_.empty())
        return size;

    measureCells(hdc);

    int rowCount = 0;
    int columnCount = 0;
    candidateGrid(static_cast<int>(items_.size()), candPerRow_, rowCount, columnCount);

    size.cx = columnCount * (selKeyWidth_ + textWidth_);
    size.cx += colSpacing_ * std::max(0, columnCount - 1);
    size.cx += margin_ * 2;
    size.cy = itemHeight_ * rowCount + rowSpacing_ * std::max(0, rowCount - 1);
    size.cy += margin_ * 2;
    return size;
}

void CandidateRenderer::itemRect(int index, RECT& rect) const {
    int rowCount = 0;
    int columnCount = 0;
    candidateGrid(static_cast<int>(items_.size()), candPerRow_, rowCount, columnCount);

    int row = rowCount > 0 ? index % rowCount : 0;
    int col = rowCount > 0 ? index / rowCount : 0;
    rect.left = margin_ + col * (selKeyWidth_ + textWidth_ + colSpacing_);
    rect.top = margin_ + row * (itemHeight_ + rowSpacing_);
    rect.right = rect.left + (selKeyWidth_ + textWidth_);
    rect.bottom = rect.top + itemHeight_;
}

int CandidateRenderer::hitTest(POINT point) const {
    for (size_t i = 0; i < items_.size(); ++i) {
        RECT cell;
        itemRect(static_cast<int>(i), cell);
        if (::PtInRect(&cell, point))
            return static_cast<int>(i);
    }
    return -1;
}

void CandidateRenderer::paintItem(HDC hdc, int index, int x, int y) const {
    RECT cell = {
        x,
        y,
        x + selKeyWidth_ + textWidth_,
        y + itemHeight_
    };
    if (useCursor_ && index == selection_) {
        RECT selected = cell;
        ::InflateRect(&selected, -scaled(2), -scaled(1));
        fillRoundRect(hdc, selected, scaled(8), kSelectedBackground);
    }
    else if (index == hover_) {
        // Drawn only where the real cursor is not, and in a lighter shade, so
        // the candidate that Enter would commit always stays the loudest thing
        // on screen.
        RECT hovered = cell;
        ::InflateRect(&hovered, -scaled(2), -scaled(1));
        fillRoundRect(hdc, hovered, scaled(8), kHoverBackground);
    }

    int textY = y + scaled(6);
    if (static_cast<size_t>(index) < selectionKeys_.size()) {
        wchar_t selKey[2] = {selectionKeys_[index], L'\0'};
        ::SetTextColor(hdc, index == selection_ ? kSelectedLabel : kLabel);
        ::TextOutW(hdc, x + scaled(8), textY, selKey, 1);
    }

    const std::wstring& item = items_[index];
    ::SetTextColor(hdc, kText);
    ::TextOutW(hdc, x + selKeyWidth_, textY, item.c_str(),
               static_cast<int>(item.length()));
}

void CandidateRenderer::paint(HDC hdc, const RECT& client) const {
    ::SetBkMode(hdc, TRANSPARENT);

    fillRoundRect(hdc, client, scaled(12), kBackground);

    HPEN borderPen = ::CreatePen(PS_SOLID, scaled(1), kBorder);
    HGDIOBJ oldPen = ::SelectObject(hdc, borderPen);
    HGDIOBJ oldBrush = ::SelectObject(hdc, ::GetStockObject(NULL_BRUSH));
    ::RoundRect(hdc, client.left, client.top, client.right - 1, client.bottom - 1,
                scaled(12), scaled(12));
    ::SelectObject(hdc, oldBrush);
    ::SelectObject(hdc, oldPen);
    ::DeleteObject(borderPen);

    for (size_t i = 0; i < items_.size(); ++i) {
        RECT cell;
        itemRect(static_cast<int>(i), cell);
        paintItem(hdc, static_cast<int>(i), cell.left, cell.top);
    }
}

} // namespace SmartPriority
