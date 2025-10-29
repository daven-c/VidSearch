import numpy as np
from PIL import Image
import cv2
import os
import torch

device = 'cuda' if torch.cuda.is_available() else 'cpu'
model, preprocesser = clip.load("ViT-B/32", device=device, jit=False)
