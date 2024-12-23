import torch
from torch import nn
from collections import OrderedDict

from utils.utils import NestedTensor, nested_tensor_from_tensor_list
from models.backbone import build_backbone
from models.transformer import build_transformer


class brain_encoder(nn.Module):
    def __init__(self, args, dataset):
        super().__init__()

        self.lr_backbone = args.lr_backbone

        self.backbone_arch = args.backbone_arch
        self.return_interm = args.return_interm
        self.encoder_arch = args.encoder_arch

        ### Brain encoding model
        # if args.encoder_arch == 'transformer':
        self.transformer = build_transformer(args)

        self.num_queries = dataset.num_parcels
        self.hidden_dim = self.transformer.d_model
        self.linear_feature_dim = self.hidden_dim

        self.enc_layers = args.enc_layers
        self.dec_layers = args.dec_layers

        self.lh_vs = args.lh_vs
        self.rh_vs = args.rh_vs

        self.query_embed = nn.Embedding(self.num_queries, self.hidden_dim)

        ### backbone_arch for feature exraction
        self.backbone_model = build_backbone(args)

        if ("resnet" in self.backbone_arch) and ("transformer" in self.encoder_arch):
            self.input_proj = nn.Conv2d(
                self.backbone_model.num_channels, self.hidden_dim, kernel_size=1
            )
        elif ("resnet" in self.backbone_arch) and ("linear" in self.encoder_arch):
            self.input_proj = nn.AdaptiveAvgPool2d(1)
            self.linear_feature_dim = self.backbone_model.num_channels

        # linear readout layers to the neural data
        self.readout_res = args.readout_res

        self.max_parcel_size = dataset.max_parcel_size
        self.num_parcels = dataset.num_parcels

        # this is a mask of shape (num_parcels, num_voxels) where each row is the voxels that belong in a parcel
        self.parcel_mask = (
            torch.stack(
                [
                    torch.zeros(dataset.num_hemi_voxels).scatter_(0, parcel, 1)
                    for parcel in dataset.parcels
                ]
            )
            .permute(1, 0)
            .to(args.device)
        )

        # parcel_mask = dataset.masks
        # weights = torch.randn(
        #     dataset.num_parcels, self.linear_feature_dim, dataset.max_parcel_size
        # )
        # weights[~parcel_mask.unsqueeze(1).expand(-1, self.linear_feature_dim, -1)] = 0
        # self.embed = torch.nn.Parameter(weights)

        # self.embed_bias = nn.Parameter(
        #     torch.randn(dataset.num_parcels, dataset.max_parcel_size)
        # )
        # self.embed_bias = torch.nn.Parameter(
        #     torch.where(
        #         parcel_mask,
        #         self.embed_bias,
        #         torch.tensor(0.0, device=self.embed_bias.device),
        #     )
        # )

        self.embed = nn.Sequential(nn.Linear(self.hidden_dim, dataset.num_hemi_voxels))

    def forward(self, samples: NestedTensor):
        if isinstance(samples, (list, torch.Tensor)):
            samples = nested_tensor_from_tensor_list(samples)
        # def forward(self, x):
        # if self.backbone_arch:
        if self.lr_backbone == 0:
            with torch.no_grad():
                features, pos = self.backbone_model(samples)
        else:
            features, pos = self.backbone_model(samples)

        input_proj_src, mask = features[-1].decompose()
        # assert mask is not None
        pos_embed = pos[-1]
        _, _, h, w = pos_embed.shape

        # if backbone is resnet, apply 1x1 conv to project the feature to the transformer dimension
        # if "resnet" in self.backbone_arch:
        #     input_proj_src = self.input_proj(input_proj_src)

        # print("input_proj_src.shape:", input_proj_src.shape)
        # print("mask.shape:", mask.shape)
        # print(mask)
        # print("pos_embed.shape:", pos_embed.shape)

        hs = self.transformer(
            input_proj_src,
            mask,
            self.query_embed.weight,
            pos_embed,
            self.return_interm,
        )
        output_tokens = hs[-1]  # TODO: 250 x 768 output tokens

        # output tokens: [batch_size, num_parcels, hidden_dim] like (bs, 500, 768)
        # weights: [num_parcels, hidden_dim, max_parcel_size] like (500, 768, 2600)
        # input to bmm: [500, bs, 768] by [500, 768, 2600]
        # print("output_tokens.shape:", output_tokens.permute(1, 0, 2).shape)
        # print("self.embed.shape:", self.embed.shape)
        # pred = torch.bmm(
        #     output_tokens.permute(1, 0, 2),
        #     self.embed,
        # )
        # shape = [num_parcels, batch_size, max_parcel_size] like (500, bs, 2600)

        # pred = pred.permute(1, 0, 2)
        # shape = [batch_size, num_parcels, max_parcel_size] like (bs, 500, 2600)
        # pred = pred + self.embed_bias

        pred = self.embed(output_tokens)
        pred = torch.movedim(pred, 1, -1)
        pred = pred * self.parcel_mask
        pred = torch.sum(pred, dim=-1)

        # if self.encoder_arch == "transformer":
        #     hs = self.transformer(
        #         input_proj_src,
        #         mask,
        #         self.query_embed.weight,
        #         pos_embed,
        #         self.return_interm,
        #     )
        #     output_tokens = hs[-1]  # TODO: 250 x 768 output tokens

        #     if self.readout_res == "voxels":
        #         lh_f_pred = self.lh_embed(output_tokens[:, 0 : self.lh_vs, :])
        #         rh_f_pred = self.rh_embed(output_tokens[:, self.lh_vs :, :])

        #         lh_f_pred = torch.diagonal(lh_f_pred, dim1=-2, dim2=-1)
        #         rh_f_pred = torch.diagonal(rh_f_pred, dim1=-2, dim2=-1)

        #     elif self.readout_res == "hemis":
        #         lh_f_pred = self.lh_embed(output_tokens[:, 0, :])
        #         rh_f_pred = self.rh_embed(output_tokens[:, 1, :])

        #     elif self.readout_res == "parcels":
        #         # output tokens: [batch_size, num_parcels, hidden_dim] like (bs, 500, 768)
        #         # weights: [num_parcels, hidden_dim, max_parcel_size] like (500, 768, 2600)
        #         # input to bmm: [500, bs, 768] by [500, 768, 2600]
        #         # print("output_tokens.shape:", output_tokens.permute(1, 0, 2).shape)
        #         # print("self.embed.shape:", self.embed.shape)
        #         pred = torch.bmm(
        #             output_tokens.permute(1, 0, 2),
        #             self.embed,
        #         )
        #         # shape = [num_parcels, batch_size, max_parcel_size] like (500, bs, 2600)

        #         pred = pred.permute(1, 0, 2)
        #         # shape = [batch_size, num_parcels, max_parcel_size] like (bs, 500, 2600)
        #         pred = pred + self.embed_bias

        #     else:
        #         lh_f_pred = self.lh_embed(output_tokens[:, :8, :])
        #         lh_f_pred = torch.movedim(lh_f_pred, 1, -1)

        #         rh_f_pred = self.rh_embed(output_tokens[:, 8:, :])
        #         rh_f_pred = torch.movedim(rh_f_pred, 1, -1)

        # elif self.encoder_arch == "linear":
        #     output_tokens = input_proj_src.squeeze()
        #     lh_f_pred = self.lh_embed(output_tokens)
        #     rh_f_pred = self.rh_embed(output_tokens)

        out = {
            # "lh_f_pred": lh_f_pred,
            # "rh_f_pred": rh_f_pred,
            "pred": pred,
            # "output_tokens": output_tokens,
        }

        return out
