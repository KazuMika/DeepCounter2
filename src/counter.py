# -*- coding: utf-8 --
import os
import threading
import random
from collections import deque
import cv2
import numpy as np
import torch
import torch.backends.cudnn as cudnn
import glob

from tracker.sort import Sort
from tracker.iou_tracking import Iou_Tracker
from pathlib import Path

from yolov5.models.experimental import attempt_load
from yolov5.utils.datasets import LoadStreams, LoadImages
from yolov5.utils.general import check_img_size, check_imshow, non_max_suppression, \
    scale_coords,  set_logging, increment_path
from yolov5.utils.torch_utils import select_device

cudnn.benchmark = True

VIDEO_FORMATS = ['mov', 'avi', 'mp4', 'mpg', 'mpeg', 'm4v', 'wmv', 'mkv']  # acceptable video suffixes


class Counter(object):
    def __init__(self, opt):
        """
        Initialize
        """

        self.opt = opt  # config
        self.cnt_down = 0
        self.line_down = 0
        self.font = cv2.FONT_HERSHEY_DUPLEX
        self.source, weights, self.view_img, self.save_txt, self.imgsz, self.save_movie = \
            opt.source, opt.weights, opt.view_img, opt.save_txt, opt.img_size, opt.save_movie
        self.save_dir = Path(increment_path(Path(opt.project) / opt.name, exist_ok=opt.exist_ok))  # increment run
        self.save_dir.mkdir(parents=True, exist_ok=True)  # make dir
        (self.save_dir / 'detected_images').mkdir(parents=True, exist_ok=True)  # make dir
        (self.save_dir / 'detected_movies').mkdir(parents=True, exist_ok=True)  # make dir
        self.mode = opt.mode
        self.counting_mode = opt.counting_mode

        # for jumpQ
        self.is_movie_opened = True
        self.queue_images = deque()

        set_logging()
        self.device = select_device(opt.device)
        self.half = self.device.type != 'cpu'  # half precision only supported on CUDA
        self.max_age = 1 if self.opt.tracking_alg == 'sort' else 3
        self.tracking_alg = opt.tracking_alg

        # Load model
        self.model = attempt_load(weights, map_location=self.device)  # load FP32 model
        self.stride = int(self.model.stride.max())  # model stride
        self.imgsz = check_img_size(self.imgsz, s=self.stride)  # check img_size
        self.names = self.model.module.names if hasattr(self.model, 'module') else self.model.names
        self.colors = [[random.randint(0, 255) for _ in range(3)] for _ in self.names]
        self.vid_path, self.vid_writer = None, None
        self.dataset = None

        if self.half:
            self.model.half()  # to FP16

        if self.device.type != 'cpu':
            self.model(torch.zeros(1, 3, self.imgsz, self.imgsz).to(self.device).type_as(next(self.model.parameters())))  # run once
        if self.mode == 'webcam':
            self.movies = []
            self.webcam = True
        else:
            self.movies = self.get_movies(self.source)
            self.webcam = False

    def get_movies(self, path):
        """
        path???????????????????????????????????????

        Parameters
        ----------
        path : str
            ?????????????????????????????????????????????????????????

        Returns
        -------
        videos : list
            DTC????????????????????????????????????????????????????????????list
        """
        p = str(Path(path).absolute())  # os-agnostic absolute path
        if '*' in p:
            files = sorted(glob.glob(p, recursive=True))  # glob
        elif os.path.isdir(p):
            files = sorted(glob.glob(os.path.join(p, '*.*')))  # dir
        elif os.path.isfile(p):
            files = [p]  # files
        else:
            raise Exception(f'ERROR: {p} does not exist')

        videos = [x for x in files if x.split('.')[-1].lower() in VIDEO_FORMATS]
        return videos

    def excute(self):
        """
        ?????????counting???????????????
        ??????????????????????????????????????????????????????
        """
        with torch.no_grad():
            if self.webcam:
                movie = '0'
                self.view_img = check_imshow()
                cudnn.benchmark = True
                self.dataset = LoadStreams(movie, img_size=self.imgsz, stride=self.stride)
                self.counting(movie)
            else:
                for movie_path in self.movies:
                    self.dataset = LoadImages(movie_path, img_size=self.imgsz, stride=self.stride)
                    self.counting(movie_path)

    def get_tracker(self, movie_path):
        """
        Sort???Iou_Tracker?????????????????????

        Parameters
        ----------
        movie_path : str
            ???????????????????????????

        Returns
        -------
        tracker : Sort or Iou_Tracker
            argparse???self.tracking_alg?????????
            Sort???Iou_Tracker?????????????????????

        """
        basename = os.path.basename(movie_path).replace('.mp4', '')
        movie_id = basename[0:4]
        self.image_dir = self.save_dir
        height = self.dataset.height
        line_down = int(9*(height/10))
        self.line_down = line_down
        tracker = None
        if self.tracking_alg == 'sort':
            tracker = Sort(max_age=self.max_age,
                           line_down=line_down,
                           movie_id=movie_id,
                           save_image_dir='./runs',
                           movie_date='',
                           basename=basename,
                           min_hits=3)
        else:
            tracker = Iou_Tracker(max_age=self.max_age,
                                  line_down=line_down,
                                  save_image_dir=self.image_dir,
                                  movie_id=movie_id,
                                  movie_date='',
                                  base_name=basename)

        return tracker

    def counting(self,  movie_path):
        """

        """

        if self.counting_mode == 'v1':
            tracker = self.get_tracker(movie_path)
        elif self.counting_mode == 'v2':
            print(len(movie_path))
            t1 = threading.Thread(target=self.jumpQ, args=(movie_path,))
            t1.start()

        for path, img, im0s, vid_cap in self.dataset:
            self.vid_cap = vid_cap

            img2 = img.copy()

            img = torch.from_numpy(img).to(self.device)
            img = img.half() if self.half else img.float()  # uint8 to fp16/32
            img /= 255.0  # 0 - 255 to 0.0 - 1.0
            if img.ndimension() == 3:
                img = img.unsqueeze(0)

            if self.counting_mode == 'v1':
                result = self.detect([img, im0s, path])
                self.cnt_down = tracker.update(result, img2)
            elif self.counting_mode == 'v2':
                self.queue_images.append([img, im0s, path, img2])

        self.is_movie_opened = False

    def jumpQ(self, movie_path):
        """
        counting????????????threading?????????
        ?????????????????????

        Parameters
        ----------
        movie_path : str
            ???????????????????????????
        """
        tracker = self.get_tracker(movie_path)
        # LC = self.l/self.frame_rate
        LC = 10.0 / 20.0
        Ps = 0.1
        Pd = 1
        Tw = 10
        w = 0
        stack_images = deque()
        while self.is_movie_opened or self.queue_images:
            if self.queue_images:
                img = self.queue_images.popleft()
                Ran = random.random()
                if len(stack_images) < 10:
                    stack_images.append(img)
                    continue

                if Ran < Pd:
                    cords = self.detect(img[:3])
                    if len(cords) >= 1:
                        Pd = 1
                        w = 0
                        while stack_images:
                            img = stack_images.popleft()
                            result = self.detect(img[:3])
                            tracker.update(result, img[3])

                    else:
                        w += 1
                        if w >= Tw:
                            Pd = max(Pd - Ps, LC)
                else:
                    if Tw > len(self.queue_images):
                        self.queue_images.append(img)
                    else:
                        self.queue_images.append(img)
                        self.queue_images.popleft()

    def detect(self, images):
        """
        yolov5???????????????

        Parameters
        ----------
        images : list
            ??????1????????????

        Returns
        -------
        result : ndarray
            yolov5???????????????????????????????????????cord???
            confidece,class???????????????????????????ndarray
        """
        img, im0s, path = images
        pred = self.model(img, augment=self.opt.augment)[0]

        pred = non_max_suppression(pred, self.opt.conf_thres, self.opt.iou_thres, classes=self.opt.classes, agnostic=self.opt.agnostic_nms)

        dets_results = []
        conf_results = []
        fps = '0'
        for i, dets in enumerate(pred):  # detections per image
            if self.webcam:  # batch_size >= 1
                p, s, im0, _ = path[i], '%g: ' % i, im0s[i].copy(), self.dataset.count
            else:
                p, s, im0, _ = path, '', im0s, getattr(self.dataset, 'frame', 0)

            p = Path(p)  # to Path
            save_path = str(self.save_dir / p.name)  # img.jpg
            s += '%gx%g ' % img.shape[2:]  # print string
            dets[:, :4] = scale_coords(img.shape[2:], dets[:, :4], im0.shape).round()
            for *det, conf, cls in reversed(dets):
                det = np.array([c.cpu().numpy() for c in det])
                det = det.astype(np.int64)
                cord = det[:4]
                dets_results.append(np.array(cord))
                conf_results.append(conf)

            if self.save_movie:
                if self.vid_path != save_path:  # new video
                    self.vid_path = save_path
                    if isinstance(self.vid_writer, cv2.VideoWriter):
                        self.vid_writer.release()  # release previous video writer
                    if self.vid_cap:  # video
                        fps = self.vid_cap.get(cv2.CAP_PROP_FPS)
                        w = int(self.vid_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        h = int(self.vid_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    else:  # stream
                        fps, w, h = 30, im0.shape[1], im0.shape[0]
                        save_path += '.mp4'
                    self.vid_writer = cv2.VideoWriter('test.mp4', cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))

                str_down = 'COUNT:' + str(self.cnt_down)
                cv2.line(im0, (0, self.line_down),
                         (int(im0.shape[1]), self.line_down), (255, 0, 0), 2)
                cv2.putText(im0, str_down, (10, 70), self.font,
                            2.0, (0, 0, 0), 10, cv2.LINE_AA)
                cv2.putText(im0, str_down, (10, 70), self.font,
                            2.0, (255, 255, 255), 8, cv2.LINE_AA)

                for d, conf in zip(dets_results, conf_results):
                    center_x = (d[0]+d[2])//2
                    center_y = (d[1]+d[3])//2
                    if self.line_down >= center_y:
                        cv2.circle(im0, (center_x, center_y), 3, (0, 0, 126), -1)
                        cv2.rectangle(
                            im0, (d[0], d[1]), (d[2], d[3]), (0, 252, 124), 2)

                        cv2.rectangle(im0, (d[0], d[1] - 20),
                                      (d[0] + 60, d[1]), (0, 252, 124), thickness=2)
                        cv2.rectangle(im0, (d[0], d[1] - 20),
                                      (d[0] + 60, d[1]), (0, 252, 124), -1)
                        cv2.putText(im0, str(int(conf.item() * 100))+'%',
                                    (d[0], d[1] - 5), self.font, 0.6, (0, 0, 0), 1, cv2.LINE_AA)

                self.vid_writer.write(im0)

        return np.array(dets_results)
