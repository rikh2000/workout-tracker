from PIL import Image, ImageDraw
import os

for size in [192, 512]:
    img = Image.new('RGB', (size, size), '#2c3e50')
    draw = ImageDraw.Draw(img)
    text = 'WT'
    draw.text((size//2, size//2), text, fill='white', anchor='mm')
    img.save(f'static/icon-{size}.png')
print('Icons created')