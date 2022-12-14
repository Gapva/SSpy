import imgui
from pathlib import Path


def set(style: imgui.core.GuiStyle):
    io = imgui.get_io()
    imgui.style_colors_dark(style)
    style.colors[imgui.COLOR_BORDER] = (1, 1, 1, 0.3)
    style.colors[imgui.COLOR_WINDOW_BACKGROUND] = (0.1, 0.1, 0.1, 0.5)
    style.colors[imgui.COLOR_TITLE_BACKGROUND] = (0.3, 0.3, 0.3, 1)
    style.colors[imgui.COLOR_TITLE_BACKGROUND_COLLAPSED] = (0.3, 0.3, 0.3, 1)
    style.colors[imgui.COLOR_TITLE_BACKGROUND_ACTIVE] = (0.3, 0.3, 0.3, 1)
    style.colors[imgui.COLOR_BUTTON_HOVERED] = (0.3, 0.3, 0.3, 1)
    style.colors[imgui.COLOR_BUTTON_ACTIVE] = (0.5, 0.5, 0.5, 1)
    style.colors[imgui.COLOR_BUTTON] = (0.2, 0.2, 0.2, 1)
    style.colors[imgui.COLOR_FRAME_BACKGROUND] = (0.15, 0.15, 0.15, 1)
    style.colors[imgui.COLOR_FRAME_BACKGROUND_ACTIVE] = (0.05, 0.05, 0.05, 1)
    style.colors[imgui.COLOR_FRAME_BACKGROUND_HOVERED] = (0.2, 0.2, 0.2, 1)
    style.colors[imgui.COLOR_POPUP_BACKGROUND] = (0.1, 0.1, 0.1, 0.9)
    style.colors[imgui.COLOR_CHECK_MARK] = (1, 1, 1, 1)
    style.colors[imgui.COLOR_HEADER] = (0.1, 0.1, 0.1, 1)
    style.colors[imgui.COLOR_HEADER_ACTIVE] = (0.2, 0.2, 0.2, 1)
    style.colors[imgui.COLOR_HEADER_HOVERED] = (0.3, 0.3, 0.3, 1)
    style.colors[imgui.COLOR_RESIZE_GRIP] = (1, 1, 1, 0)
    style.colors[imgui.COLOR_RESIZE_GRIP_HOVERED] = (1, 1, 1, 0.1)
    style.colors[imgui.COLOR_RESIZE_GRIP_ACTIVE] = (1, 1, 1, 0.1)
    style.colors[imgui.COLOR_MENUBAR_BACKGROUND] = (1, 1, 1, 0.1)
    style.colors[imgui.COLOR_TEXT_SELECTED_BACKGROUND] = (1, 1, 1, 0.3)
    style.popup_rounding = 4
    style.window_rounding = 4
    style.child_rounding = 2
    style.grab_rounding = 2
    style.frame_rounding = 2
    style.frame_border_size = 0
    style.child_border_size = 0
    style.window_border_size = 0
    style.window_min_size = (150, 176)
    return io.fonts.add_font_default(), io.fonts.add_font_from_file_ttf(
        str(Path(__file__).parent.parent.joinpath("assets", "DroidSans.ttf")), 20
    )
