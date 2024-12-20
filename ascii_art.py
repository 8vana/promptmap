from PIL import Image


def gradient_color(start_color, end_color, steps):
    """
    Generate a gradient list of colors between start_color and end_color.
    """
    gradient = []
    for i in range(steps):
        r = int(start_color[0] + (end_color[0] - start_color[0]) * i / (steps - 1))
        g = int(start_color[1] + (end_color[1] - start_color[1]) * i / (steps - 1))
        b = int(start_color[2] + (end_color[2] - start_color[2]) * i / (steps - 1))
        gradient.append((r, g, b))
    return gradient


def image_to_colored_ascii_with_promptmap():
    """
    Generate a ASCII ART for promptmap.
    """
    # Character set.
    chars = "@%#*+=-:. "
    scale = len(chars) / 256

    # Banner width.
    width = 80

    # 画像を開く
    img = Image.open("./assets/images/promptmap_logo.png")
    img = img.resize((width, int(img.height / img.width * width * 0.55)))
    img = img.convert("RGB")

    # Load image.
    pixels = img.load()

    # Generate colored ASCII ART.
    ascii_art = ""
    for y in range(img.height):
        for x in range(img.width):
            r, g, b = pixels[x, y]
            grayscale = int((r + g + b) / 3)
            char = chars[int(grayscale * scale)]
            ascii_art += f"\033[38;2;{r};{g};{b}m{char}\033[0m"
        ascii_art += "\n"

    # ASCII ART for promptmap.
    promptmap_art = [
        "██████╗ ██████╗  ██████╗ ███╗   ███╗██████╗ ████████╗███╗   ███╗ █████╗ ██████╗",
        "██╔══██╗██╔══██╗██╔═══██╗████╗ ████║██╔══██╗╚══██╔══╝████╗ ████║██╔══██╗██╔══██╗",
        "██████╔╝██████╔╝██║   ██║██╔████╔██║██████╔╝   ██║   ██╔████╔██║███████║██████╔╝",
        "██╔═══╝ ██╔══██╗██║   ██║██║╚██╔╝██║██╔═══╝    ██║   ██║╚██╔╝██║██╔══██║██╔═══╝ ",
        "██║     ██║  ██║╚██████╔╝██║ ╚═╝ ██║██║        ██║   ██║ ╚═╝ ██║██║  ██║██║     ",
        "╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝     ╚═╝╚═╝        ╚═╝   ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝     "
    ]

    # Set gradient (start: blue, end: red)
    start_color = (0, 0, 255)  # blue.
    end_color = (255, 0, 0)    # red.
    gradient = gradient_color(start_color, end_color, len(promptmap_art))

    # Generate colored "promptmap".
    promptmap_colored = ""
    for i, line in enumerate(promptmap_art):
        r, g, b = gradient[i]
        promptmap_colored += f"\033[38;2;{r};{g};{b}m{line}\033[0m\n"

    # Show ASCII ART.
    ascii_art += "\n" + promptmap_colored
    print(ascii_art)
