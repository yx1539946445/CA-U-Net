import numpy as np
import torch
from torch.nn import functional as F
from monai.networks.layers import Conv, ChannelPad
from torch import nn
from typing import Callable, Tuple, List
import pytorch_lightning as pl
import asamseg.utils as myut

from asamseg.attention_packages import CoordAttention, AxialAttention, EfficientAttention, SpatialAttention, \
    CrissCrossAttention, sa_layer, ACmix, SimAM, CBAM, PsAAttention, NAM, SpatialAttentionModule, selfattention

'''
   BN 就是批量归一化

   RELU 就是激活函数

   lambda x:x 这个函数的意思是输出等于输入

   identity 就是残差

   1个resnet block 包含2个basic block
   1个resnet block 需要添加2个残差

   在resnet block之间残差形式是1*1conv，在resnet block内部残差形式是lambda x:x
   resnet block之间的残差用粗箭头表示，resnet block内部的残差用细箭头表示

   3*3conv s=2，p=1 特征图尺寸会缩小
   3*3conv s=1，p=1 特征图尺寸不变
'''

'''SA '''
import torch
import torch.nn as nn
from torchvision import datasets, transforms
from torchvision import models

###########################################################################
# Created by: Hang Zhang
# Email: zhang.hang@rutgers.edu
# Copyright (c) 2017
###########################################################################

import math
import numpy as np

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn.parallel.data_parallel import DataParallel
from torch.nn.parallel.parallel_apply import parallel_apply
from torch.nn.parallel.scatter_gather import scatter

from .resnet import base_resnet



class PyramidPool(nn.Module):
    def __init__(self, in_channels, out_channels, pool_size):
        super(PyramidPool, self).__init__()
        self.features = nn.Sequential(
            nn.AdaptiveAvgPool2d(pool_size),
            nn.Conv2d(in_channels, out_channels, 1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )

    def forward(self, x):
        size = x.shape
        output = nn.functional.interpolate(self.features(x), size[2:], mode='bilinear', align_corners=True)
        return output


class PPM(nn.ModuleList):
    def __init__(self, pool_sizes, in_channels, out_channels):
        super(PPM, self).__init__()
        self.pool_sizes = pool_sizes
        self.in_channels = in_channels
        self.out_channels = out_channels

        for pool_size in pool_sizes:
            self.append(
                nn.Sequential(
                    nn.AdaptiveMaxPool2d(pool_size),
                    nn.Conv2d(self.in_channels, self.out_channels, kernel_size=1),
                )
            )

    def forward(self, x):
        out_puts = []
        for ppm in self:
            ppm_out = nn.functional.interpolate(ppm(x), size=x.size()[-2:], mode='bilinear', align_corners=True)
            out_puts.append(ppm_out)
        return out_puts


class SPHEAD(nn.Module):
    def __init__(self, in_channels, out_channels):
        super(SPHEAD, self).__init__()
        inter_channels = in_channels // 2
        self.trans_layer = nn.Sequential(nn.Conv2d(in_channels, inter_channels, 1, 1, 0, bias=False),
                                         nn.BatchNorm2d(inter_channels),
                                         nn.ReLU(True)
                                         )
        self.strip_pool1 = StripPooling(inter_channels, (20, 12))
        self.strip_pool2 = StripPooling(inter_channels, (20, 12))
        self.score_layer = nn.Sequential(nn.Conv2d(inter_channels, inter_channels // 2, 3, 1, 1, bias=False),
                                         nn.BatchNorm2d(inter_channels // 2),
                                         nn.ReLU(True),
                                         nn.Dropout2d(0.1, False),
                                         nn.Conv2d(inter_channels // 2, out_channels, 1)
                                         )

    def forward(self, x):
        x = self.trans_layer(x)
        x = self.strip_pool1(x)
        x = self.strip_pool2(x)
        x = self.score_layer(x)
        return x

class StripPooling(nn.Module):
    """
    Reference:
    """
    def __init__(self, in_channels, pool_size):
        super(StripPooling, self).__init__()
        self.pool1 = nn.AdaptiveAvgPool2d(pool_size[0])
        self.pool2 = nn.AdaptiveAvgPool2d(pool_size[1])
        self.pool3 = nn.AdaptiveAvgPool2d((1, None))
        self.pool4 = nn.AdaptiveAvgPool2d((None, 1))

        inter_channels = int(in_channels/4)
        self.conv1_1 = nn.Sequential(nn.Conv2d(in_channels, inter_channels, 1, bias=False),
                                     nn.BatchNorm2d(inter_channels),
                                     nn.ReLU(True))
        self.conv1_2 = nn.Sequential(nn.Conv2d(in_channels, inter_channels, 1, bias=False),
                                     nn.BatchNorm2d(inter_channels),
                                     nn.ReLU(True))
        self.conv2_0 = nn.Sequential(nn.Conv2d(inter_channels, inter_channels, 3, 1, 1, bias=False),
                                     nn.BatchNorm2d(inter_channels))
        self.conv2_1 = nn.Sequential(nn.Conv2d(inter_channels, inter_channels, 3, 1, 1, bias=False),
                                     nn.BatchNorm2d(inter_channels))
        self.conv2_2 = nn.Sequential(nn.Conv2d(inter_channels, inter_channels, 3, 1, 1, bias=False),
                                     nn.BatchNorm2d(inter_channels))
        self.conv2_3 = nn.Sequential(nn.Conv2d(inter_channels, inter_channels, (1, 3), 1, (0, 1), bias=False),
                                     nn.BatchNorm2d(inter_channels))
        self.conv2_4 = nn.Sequential(nn.Conv2d(inter_channels, inter_channels, (3, 1), 1, (1, 0), bias=False),
                                     nn.BatchNorm2d(inter_channels))
        self.conv2_5 = nn.Sequential(nn.Conv2d(inter_channels, inter_channels, 3, 1, 1, bias=False),
                                     nn.BatchNorm2d(inter_channels),
                                     nn.ReLU(True))
        self.conv2_6 = nn.Sequential(nn.Conv2d(inter_channels, inter_channels, 3, 1, 1, bias=False),
                                     nn.BatchNorm2d(inter_channels),
                                     nn.ReLU(True))
        self.conv3 = nn.Sequential(nn.Conv2d(inter_channels*2, in_channels, 1, bias=False),
                                   nn.BatchNorm2d(in_channels))
        # bilinear interpolate options

    def forward(self, x):
        _, _, h, w = x.size()
        x1 = self.conv1_1(x)
        x2 = self.conv1_2(x)
        x2_1 = self.conv2_0(x1)
        x2_2 = F.interpolate(self.conv2_1(self.pool1(x1)), (h, w), )
        x2_3 = F.interpolate(self.conv2_2(self.pool2(x1)), (h, w), )
        x2_4 = F.interpolate(self.conv2_3(self.pool3(x2)), (h, w), )
        x2_5 = F.interpolate(self.conv2_4(self.pool4(x2)), (h, w), )
        x1 = self.conv2_5(F.relu_(x2_1 + x2_2 + x2_3))
        x2 = self.conv2_6(F.relu_(x2_5 + x2_4))
        out = self.conv3(torch.cat([x1, x2], dim=1))
        return F.relu_(x + out)

###########################################################################
# Created by: Hang Zhang
# Email: zhang.hang@rutgers.edu
# Copyright (c) 2017
###########################################################################
import os
import numpy as np
import torch
import torch.nn as nn
from torch.nn.functional import interpolate
#from ..nn import ConcurrentModule, SyncBatchNorm

class GlobalPooling(nn.Module):
    def __init__(self, in_channels, out_channels):
        super(GlobalPooling, self).__init__()
        self.gap = nn.Sequential(nn.AdaptiveAvgPool2d(1),
                                 nn.Conv2d(in_channels, out_channels, 1, bias=False),
                                 nn.BatchNorm2d(out_channels),
                                 nn.ReLU(True))

    def forward(self, x):
        _, _, h, w = x.size()
        pool = self.gap(x)
        return F.interpolate(pool, (h,w))


class FCNHead(nn.Module):
    def __init__(self, in_channels, out_channels, with_global=False):
        super(FCNHead, self).__init__()
        inter_channels = in_channels // 4
        if with_global:
            self.conv5 = nn.Sequential(nn.Conv2d(in_channels, inter_channels, 3, padding=1, bias=False),
                                       nn.BatchNorm2d(inter_channels),
                                       nn.ReLU(),
                                       GlobalPooling(inter_channels, inter_channels),
                                       nn.Dropout2d(0.1, False),
                                       nn.Conv2d(2*inter_channels, out_channels, 1))
        else:
            self.conv5 = nn.Sequential(nn.Conv2d(in_channels, inter_channels, 3, padding=1, bias=False),
                                       nn.BatchNorm2d(inter_channels),
                                       nn.ReLU(),
                                       nn.Dropout2d(0.1, False),
                                       nn.Conv2d(inter_channels, out_channels, 1))

    def forward(self, x):
        return self.conv5(x)


class my_spnet(pl.LightningModule):
    def __init__(self,
                 in_channels: int,
                 out_channels: int,
                 extra_gap_weight: float,
                 learning_rate: float = 1.0e-3,
                 loss_func: Callable = nn.CrossEntropyLoss(),
                 total_iterations: int = 1000,
                 ):
        super(my_spnet, self).__init__()
        self.fcn = base_resnet()
        self.aux_loss = False

        self.aux_loss = True
        self.aux_head = FCNHead(in_channels=1024,out_channels=out_channels)
        self.cls_seg = nn.Sequential(
            SPHEAD(in_channels=2048, out_channels=out_channels),
        )

        self.extra_gap_weight = extra_gap_weight
        self.learning_rate = learning_rate
        self.loss_func = loss_func
        self.total_iterations = total_iterations

    def forward(self, x):
        size = x.shape
        aux, encoder_x_first = self.fcn(x)
        if self.training:
            aux = self.aux_head(aux)
            aux = nn.functional.interpolate(aux, size[2:], mode='bilinear', align_corners=True)
            x = self.cls_seg(encoder_x_first)
            x = nn.functional.interpolate(x, size[2:], mode='bilinear', align_corners=True)
            return aux, x
        else:
            x = self.cls_seg(encoder_x_first)
            x = nn.functional.interpolate(x, size[2:], mode='bilinear', align_corners=True)
            return x

    def training_step(self, batch, batch_idx):
        loss = None
        if self.extra_gap_weight is None:
            loss = myut.cal_batch_loss_aux(self, batch, self.loss_func, use_sliding_window=False)
        else:
            loss = myut.cal_batch_loss_aux_gap(self, batch, self.loss_func, use_sliding_window=False)
        self.log('train_loss', loss, on_step=True, on_epoch=True, prog_bar=True, logger=True)
        return loss

    def validation_step(self, batch, batch_idx):
        loss = None
        if self.extra_gap_weight is None:
            loss = myut.cal_batch_loss(self, batch, self.loss_func, use_sliding_window=True)
        else:
            loss = myut.cal_batch_loss_gap(self, batch, loss_func= self.loss_func,extra_gap_weight=self.extra_gap_weight, use_sliding_window=True)
        self.log('val_loss', loss, on_epoch=True, prog_bar=True, logger=True)
        return loss

    def optimizer_step(
            self, epoch, batch_idx, optimizer, optimizer_idx, optimizer_closure,
            on_tpu=False, using_native_amp=False, using_lbfgs=False,
    ):
        initial_learning_rate = self.learning_rate
        current_iteration = self.trainer.global_step
        total_iteration = self.total_iterations
        for pg in optimizer.param_groups:
            pg['lr'] = myut.poly_learning_rate(initial_learning_rate, current_iteration, total_iteration)
        optimizer.step(closure=optimizer_closure)

    def configure_optimizers(self):
        return myut.configure_optimizers(self, self.learning_rate)
