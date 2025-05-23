import os
import nibabel as nib
import numpy as np
import torch
import torchvision.transforms as T
from torchvision import datasets
from torch.utils.data import Dataset

from data.librispeech import LIBRISPEECH
from data.era5 import ERA5
from data.videofolder import VideoFolderDataset

DATA_PATH = '/home/jmcginnis/git_repositories/GradNCP/data'


class ImgDataset(Dataset):
    def __init__(self, data, sdf=False):
        self.data = data
        self.sdf = sdf

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        x = self.data[idx]
        if not self.sdf:
            x = x[0]
        return {
            'imgs': x,
        }


class ImageFolder(datasets.ImageFolder):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __getitem__(self, index):
        path, target = self.samples[index]
        sample = self.loader(path)
        if self.transform is not None:
            sample = self.transform(sample)

        return {
            'imgs': sample,
        }



import torch.nn as nn

class SheppLoganDataset(Dataset):
    def __init__(self, root_dir, transform=None, img_size=128):
        self.root_dir = root_dir
        self.subjects = sorted(os.listdir(root_dir))  # Each subject folder
        self.transform = transform
        self.img_size = img_size

        if self.img_size == 128:
            self.downsample = nn.AvgPool3d(kernel_size=2, stride=2)
        else:
            self.downsample = None

    def __len__(self):
        return len(self.subjects)

    def __getitem__(self, idx):
        subject_path = os.path.join(self.root_dir, self.subjects[idx])

        t1 = nib.load(os.path.join(subject_path, 'T1w.nii.gz')).get_fdata()
        t2 = nib.load(os.path.join(subject_path, 'T2w.nii.gz')).get_fdata()
        flair = nib.load(os.path.join(subject_path, 'FLAIR.nii.gz')).get_fdata()

        t1 = torch.from_numpy(t1)
        t2 = torch.from_numpy(t2)
        flair = torch.from_numpy(flair)

        if self.downsample:
            t1= self.downsample(t1.unsqueeze(0))
            t2= self.downsample(t2.unsqueeze(0))
            flair= self.downsample(flair.unsqueeze(0))

        #print("Flair Shape:")
        #print(flair.shape)

        def normalize(x):
            #x = x.astype(np.float32)
            return (x - torch.min(x)) / (torch.max(x) - torch.min(x) + 1e-5)

        stacked = np.stack([normalize(t1), normalize(t2), normalize(flair)], axis=0)  # (3, H, W, D)
        stacked_tensor = torch.from_numpy(stacked).float().unsqueeze(0)  # (1, 3, H, W, D)

        #print("Stacked Shape:")
        #print(stacked_tensor.shape)

        #if self.downsample:
        #    stacked_tensor = self.downsample(stacked_tensor)  # (1, 3, H', W', D')
        #stacked_tensor = stacked_tensor.squeeze(0)  # (3, H', W', D')

        if self.transform:
            stacked_tensor = self.transform(stacked_tensor)

        return {
            'img': stacked_tensor
        }



def get_dataset(P, dataset, only_test=False):
    """
    Load dataloaders for an image dataset, center-cropped to a resolution.
    """
    val_set = None
    P.data_size = None

    if dataset == 'celeba':
        T_base = T.Compose([
            T.Resize(178),
            T.CenterCrop(178),
            T.ToTensor()
        ])
        train_set = ImgDataset(
            datasets.CelebA(DATA_PATH, split='train',
                            target_type='attr', transform=T_base, download=False)
        )
        test_set = ImgDataset(
            datasets.CelebA(DATA_PATH, split='test',
                            target_type='attr', transform=T_base, download=False)
        )
        P.data_type = 'img'
        P.dim_in, P.dim_out = 2, 3
        P.data_size = (3, 178, 178)

    elif dataset == 'imagenette2_320':

        if P.transfer == True:
            print("TRANSFER resize")
            T_base = T.Compose([
                T.Resize(128),
                T.CenterCrop(128),
                T.ToTensor()
            ])
        else:
            T_base = T.Compose([
                T.Resize(178),
                T.CenterCrop(178),
                T.ToTensor()
            ])

        train_dir = os.path.join(DATA_PATH, 'imagenette2-320', 'train')
        train_set = ImgDataset(
            datasets.ImageFolder(train_dir, transform=T_base)
        )
        test_dir = os.path.join(DATA_PATH, 'imagenette2-320', 'val')
        test_set = ImgDataset(
            datasets.ImageFolder(test_dir, transform=T_base)
        )
        P.data_type = 'img'
        P.dim_in, P.dim_out = 2, 3
        P.data_size = (3, 178, 178)

    elif dataset == 'text':
        sdf = np.load(f'{DATA_PATH}/data_2d_text.npz')

        # numpy and torch images have different channel axis
        sdf_train = np.transpose(sdf['train_data.npy'], (0, 3, 1, 2)).astype(np.float32) / 255.
        sdf_test = np.transpose(sdf['test_data.npy'], (0, 3, 1, 2)).astype(np.float32) / 255.

        train_set = ImgDataset(torch.from_numpy(sdf_train).float(), sdf=True)
        test_set = ImgDataset(torch.from_numpy(sdf_test).float(), sdf=True)

        P.data_type = 'img'
        P.dim_in, P.dim_out = 2, 3
        P.data_size = (3, 178, 178)

    elif dataset == 'shepp_logan':
        shepp_root = os.path.join(DATA_PATH, 'shepp_logan')
        train_set = SheppLoganDataset(os.path.join(shepp_root, 'train'))
        test_set = SheppLoganDataset(os.path.join(shepp_root, 'test'))

        P.data_type = 'img3d'
        P.dim_in, P.dim_out = 3, 3
        # P.data_size = (3, 45, 52, 45)  # adjust this based on your actual NIfTI resolution
        # P.data_size = (3, 22, 27, 22)
        # P.data_size = (3, 182, 218, 182)
        P.data_size = (3, 91, 109, 91)

    elif dataset == 'celebahq1024':
        T_base = T.Compose([
            T.Resize(1024),
            T.CenterCrop(1024),
            T.ToTensor()
        ])

        train_dir = os.path.join(DATA_PATH, 'CelebA-HQ-split', 'train')
        train_set = ImgDataset(
            datasets.ImageFolder(train_dir, transform=T_base)
        )
        test_dir = os.path.join(DATA_PATH, 'CelebA-HQ-split', 'test')
        test_set = ImgDataset(
            datasets.ImageFolder(test_dir, transform=T_base)
        )
        P.data_type = 'img'
        P.dim_in, P.dim_out = 2, 3
        P.data_size = (3, 1024, 1024)

    elif dataset == 'afhq':
        T_base = T.Compose([
            T.Resize(512),
            T.CenterCrop(512),
            T.ToTensor()
        ])

        train_dir = os.path.join(DATA_PATH, 'afhq-v2', 'train')
        train_set = ImgDataset(
            datasets.ImageFolder(train_dir, transform=T_base)
        )
        test_dir = os.path.join(DATA_PATH, 'afhq-v2', 'test')
        test_set = ImgDataset(
            datasets.ImageFolder(test_dir, transform=T_base)
        )
        P.data_type = 'img'
        P.dim_in, P.dim_out = 2, 3
        P.data_size = (3, 512, 512)

    elif dataset == 'librispeech1':
        P.data_size = (1, 16000)
        P.dim_in, P.dim_out = 1, 1
        P.data_type = 'audio'
        train_set = LIBRISPEECH(root=DATA_PATH, url="train-clean-100", num_secs=1, download=True)
        test_set = LIBRISPEECH(root=DATA_PATH, url="test-clean", num_secs=1, download=True)

    elif dataset == 'librispeech3':
        P.data_size = (1, 48000)
        P.dim_in, P.dim_out = 1, 1
        P.data_type = 'audio'
        train_set = LIBRISPEECH(root=DATA_PATH, url="train-clean-100", num_secs=3, download=True)
        test_set = LIBRISPEECH(root=DATA_PATH, url="test-clean", num_secs=3, download=True)

    elif dataset == 'era5':
        P.data_size = (1, 46, 90)
        P.dim_in, P.dim_out = 3, 1
        P.data_type = 'manifold'
        data_root = os.path.join(DATA_PATH, 'era5')
        train_set = ERA5(root=data_root, split="train")
        val_set = ERA5(root=data_root, split="val")
        test_set = ERA5(root=data_root, split="test")

    elif dataset == "ucf101":

        timesteps = P.timesteps
        resolution = P.resolution

        data_path = os.path.join(DATA_PATH, 'UCF-101')
        train_set = VideoFolderDataset(data_path,
                        train=True, resolution=resolution, n_frames=timesteps, seed=P.seed
                    )
        test_set = VideoFolderDataset(data_path,
                        train=False, resolution=resolution, n_frames=timesteps, seed=P.seed
                    )

        P.data_type = 'video'
        P.dim_in, P.dim_out = 3, 3
        P.data_size = (3, timesteps, resolution, resolution)

    else:
        raise NotImplementedError()

    P.train_set = train_set

    if only_test:
        return test_set

    val_set = test_set if val_set is None else val_set
    return train_set, val_set
