import numpy as np
import torch

from .deep.feature_extractor import Extractor
from .sort.nn_matching import NearestNeighborDistanceMetric
from .sort.preprocessing import non_max_suppression
from .sort.detection import Detection
from .sort.tracker import Tracker


__all__ = ['DeepSort']


class DeepSort(object):
    def __init__(self, model_path, max_dist=0.2, min_confidence=0.3, nms_max_overlap=1.0, max_iou_distance=0.7, max_age=70, n_init=3, nn_budget=100, use_cuda=True):
        self.min_confidence = min_confidence
        self.nms_max_overlap = nms_max_overlap

        self.extractor = Extractor(model_path, use_cuda=use_cuda)

        max_cosine_distance = max_dist
        nn_budget = 100
        metric = NearestNeighborDistanceMetric("cosine", max_cosine_distance, nn_budget)
        self.tracker = Tracker(metric, max_iou_distance=max_iou_distance, max_age=max_age, n_init=n_init)

    def update(self, bbox_tlbr, confidences, ori_img):
        self.height, self.width = ori_img.shape[:2]
        # generate detections
        bboxes_tlwh = self._tlbr_to_tlwh(bbox_tlbr)
        bboxes_xywh = self._tlbr_to_xywh(bbox_tlbr)
        features = self._get_features(bbox_tlbr, ori_img)
        detections = [Detection(bboxes_tlwh[i], conf, features[i]) for i,conf in enumerate(confidences) if conf>self.min_confidence]

        # run on non-maximum supression
        boxes = np.array([d.tlwh for d in detections])
        scores = np.array([d.confidence for d in detections])
        indices = non_max_suppression(boxes, self.nms_max_overlap, scores)
        detections = [detections[i] for i in indices]

        # update tracker
        self.tracker.predict()
        self.tracker.update(detections)

        # output bbox identities
        outputs = []
        for track in self.tracker.tracks:
            if not track.is_confirmed() or track.time_since_update > 1:
                continue
            if track.is_confirmed() and not track.is_inserted()

            box = track.to_tlwh()
            x1,y1,x2,y2 = self._tlwh_to_xyxy(box)
            track_id = track.track_id
            outputs.append(np.array([x1,y1,x2,y2,track_id], dtype=np.int))
        if len(outputs) > 0:
            outputs = np.stack(outputs,axis=0)
        return outputs


    """
    TODO:
        Convert bbox from xc_yc_w_h to xtl_ytl_w_h
    Thanks JieChen91@github.com for reporting this bug!
    """
    @staticmethod
    def _xywh_to_tlwh(bbox_xywh):
        if isinstance(bbox_xywh, np.ndarray):
            bbox_tlwh = bbox_xywh.copy()
        elif isinstance(bbox_xywh, torch.Tensor):
            bbox_tlwh = bbox_xywh.clone()
        bbox_tlwh[:,0] = bbox_xywh[:,0] - bbox_xywh[:,2]/2. #x - w/2 100 - 200/2tl_x:0
        bbox_tlwh[:,1] = bbox_xywh[:,1] - bbox_xywh[:,3]/2. #y - h/2 tl_y:0
        return bbox_tlwh
    
    def _tlbr_to_xywh(self, bbox_tlbr):
        list_boxes = []
        for box in bbox_tlbr:
            temp_box = []
            xc = (box[0]+box[2])/2
            yc = (box[1]+box[3])/2
            w = box[3]-box[0]
            h = box[4]-box[1]
            temp_box.append(xc)
            temp_box.append(yc)
            temp_box.append(w)
            temp_box.append(h)
            list_boxes.append(temp_box)
        list_boxes_np_array = np.array([np.array(element) for element in list_boxes])
        return list_boxes_np_array


    def _xywh_to_xyxy(self, bbox_xywh):
        x,y,w,h = bbox_xywh
        x1 = max(int(x-w/2),0) # 0
        x2 = min(int(x+w/2),self.width-1) #150
        y1 = max(int(y-h/2),0) # 0
        y2 = min(int(y+h/2),self.height-1) #150
        return x1,y1,x2,y2

    def _tlbr_to_tlwh(self, bbox_tlbr):
        list_boxes = []
        for box in bbox_tlbr:
            temp_box = []
            x_tl = box[0]
            y_tl = box[1]
            w = box[2]-box[0]
            h = box[3] - box[1]
            temp_box.append(x_tl)
            temp_box.append(y_tl)
            temp_box.append(w)
            temp_box.append(h)
            list_boxes.append(temp_box)
        list_boxes_np_array = np.array([np.array(element) for element in list_boxes])
        return list_boxes_np_array


    def _tlwh_to_xyxy(self, bbox_tlwh):
        """
        TODO:
            Convert bbox from xtl_ytl_w_h to xc_yc_w_h
        """
        x,y,w,h = bbox_tlwh
        # x1 = max(int(x),0) + w/2
        # x2 = min(int(x+w),self.width-1) + w/2
        # y1 = max(int(y),0) + h/4
        # y2 = min(int(y+h),self.height-1) + h/2
        x1 = max(int(x), 0)
        x2 = min(int(x + w), self.width - 1)
        y1 = max(int(y), 0)
        y2 = min(int(y + h), self.height - 1)
        return x1,y1,x2,y2
    
    def     _get_features(self, bbox_tlbr, ori_img):
        im_crops = []
        for box in bbox_tlbr:
            x1,y1,x2,y2 = box[0], box[1], box[2], box[3]
            im = ori_img[y1:y2,x1:x2]
            im_crops.append(im)
        if im_crops:
            features = self.extractor(im_crops)
        else:
            features = np.array([])
        return features

