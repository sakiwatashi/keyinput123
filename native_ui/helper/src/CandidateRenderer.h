//
//    Layout and painting for the Japanese-inspired candidate grid.
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
// The TSF plumbing of the original class is deliberately absent: this renderer
// runs in a helper process that never loads into another application, so it
// implements no COM interfaces and owns no edit session.

#ifndef SMARTPRIORITY_CANDIDATE_RENDERER_H
#define SMARTPRIORITY_CANDIDATE_RENDERER_H

#ifndef NOMINMAX
#define NOMINMAX
#endif

#include <windows.h>

#include <string>
#include <vector>

namespace SmartPriority {

// Fill order for a page of candidates. The product contract is vertical-first:
// the left column holds 1-5 from top to bottom and the right column 6-0.
// Stock PIME fills row-major instead, which is the regression this exists to
// correct, so this function must never fall back to a row-major layout.
void candidateGrid(int itemCount, int maxColumns, int& rows, int& columns);

class CandidateRenderer {
public:
    CandidateRenderer();
    ~CandidateRenderer();

    void setDpi(int dpi);
    void setCandidates(const std::vector<std::wstring>& items,
                       const std::wstring& selectionKeys);
    void setSelection(int selection);
    // The mouse is tracked separately from selection_. They are different
    // facts: selection_ mirrors the input method's real cursor, which is what
    // Enter and Space commit, while the hover only previews what a click would
    // pick. Letting the mouse write selection_ made the arrow keys look dead
    // whenever the pointer rested over the window, and worse, what was
    // highlighted stopped matching what would actually be sent.
    void setHover(int hover);
    int hover() const { return hover_; }
    void setCandPerRow(int candPerRow);
    void setUseCursor(bool useCursor);

    int selection() const { return selection_; }
    size_t count() const { return items_.size(); }

    // Measures the natural window size for the current candidates. Needs a DC
    // only to measure text, and never mutates any window.
    SIZE measure(HDC hdc) const;

    void paint(HDC hdc, const RECT& client) const;

    void itemRect(int index, RECT& rect) const;
    int hitTest(POINT point) const;

private:
    int scaled(int value) const;
    void paintItem(HDC hdc, int index, int x, int y) const;
    void measureCells(HDC hdc) const;

    std::vector<std::wstring> items_;
    std::wstring selectionKeys_;
    int selection_;
    int hover_;
    int candPerRow_;
    bool useCursor_;
    int dpi_;

    // Cell metrics are derived from the current font and candidates. They are
    // cached during measure() and reused while painting the same content.
    mutable int selKeyWidth_;
    mutable int textWidth_;
    mutable int itemHeight_;
    mutable int margin_;
    mutable int rowSpacing_;
    mutable int colSpacing_;
};

} // namespace SmartPriority

#endif
