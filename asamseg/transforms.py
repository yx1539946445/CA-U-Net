
import cv2
import numpy as np
import albumentations as A
import asamseg.utils as myut


class Augumentation():
    '''
    Data augumentation.
    '''

    def __init__(self):
        self.trans = A.Compose([
            A.Rotate(limit=90, p=0.5),
            A.RandomScale(0.5, p=0.5),
            A.RandomCrop(width=256, height=256),
            A.HorizontalFlip(p=0.5),
            A.VerticalFlip(p=0.5),
            A.Transpose(p=0.5),
            A.OneOf([
                A.GaussNoise(),
                A.MultiplicativeNoise()
            ], p=0.5),
            A.OneOf([
                A.MedianBlur(),
                A.MotionBlur()
            ], p=0.5),
            A.OpticalDistortion(p=0.5),
            A.OneOf([
                A.CLAHE(),
                A.RandomGamma(),
                A.Sharpen(),
                A.RandomBrightnessContrast(),
            ], p=0.5),
        ])

    def __call__(self, img_dict):
        result = self.trans(image=img_dict['image'], mask=img_dict['label'])
        img_dict['image'] = result['image']
        img_dict['label'] = result['mask']
        return img_dict


class InstanceToBinaryLabel():
    """
    Convert instance image to binary label.
    """

    def __call__(self, img_dict):
        mask = myut.instance_to_mask(img_dict['label'])
        mask = myut.instance_mask_to_binary_label(mask)
        img_dict['label'] = mask
        return img_dict


class RGBToMaskLabel():
    """
    Convert rgb label image to mask label.
    """

    def __call__(self, img_dict):
        mask = myut.instance_to_mask(img_dict['label'])
        img_dict['label'] = mask
        return img_dict


class ConvertLabelAndGenerateGapV2():
    """
    Convert instance label to binary label, and generate gap label.
    """

    def __call__(self, img_dict):
        mask = myut.instance_to_mask(img_dict['label'])
        _, dilated_instance_list = myut.get_instance_list(mask)
        gap_map = myut.get_gap_map(dilated_instance_list, mask)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        gap_map = cv2.dilate(gap_map.astype(np.uint8), kernel=kernel, iterations=1)
        mask = myut.instance_mask_to_binary_label(mask)
        gap_map = myut.clean_gap_map(gap_map, mask)
        img_dict['label'] = mask
        img_dict['gap_map'] = gap_map.astype(np.uint8)
        return img_dict


class Normalize():
    def __init__(self, mean, std):
        self.trans = A.Normalize(mean=mean, std=std)

    def __call__(self, img_dict):
        result = self.trans(image=img_dict['image'])
        img_dict['image'] = result['image']
        return img_dict


class CenterCropForVisualize():
    def __init__(self):
        self.trans = A.CenterCrop(448, 448)

        # 42
        # self.trans = A.CenterCrop(800, 608)
        # 02
        # self.trans = A.CenterCrop(720, 1088)

    def __call__(self, img_dict):
        result = self.trans(image=img_dict['image'], mask=img_dict['label'])
        img_dict['image'] = result['image']
        img_dict['label'] = result['mask']
        return img_dict
