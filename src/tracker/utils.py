# -*- coding: utf-8 -*-
import cv2
import numpy as np
import tracker
import os


def creat_detected_image(frame, trk, line_down, cnt_down, save_image_name, font=cv2.FONT_HERSHEY_DUPLEX):
    if isinstance(trk, tracker.sort.KalmanBoxTracker):
        x, y = trk.center_cord()
        d = trk.get_state()[0].astype(np.int)
    elif isinstance(trk, tracker.trash.Trash):
        x, y = trk.center[0], trk.center[1]
        d = trk.cords[:]
    else:
        raise TypeError('{} is not supported'.format(type(trk)))

    cv2.circle(frame, (x, y), 3, (0, 0, 126), -1)
    cv2.rectangle(
        frame, (d[0], d[1]), (d[2], d[3]), (0, 252, 124), 2)

    cv2.rectangle(frame, (d[0], d[1] - 20),
                  (d[0] + 170, d[1]), (0, 252, 124), thickness=2)
    cv2.rectangle(frame, (d[0], d[1] - 20),
                  (d[0] + 170, d[1]), (0, 252, 124), -1)
    cv2.putText(frame, str(trk.id+1),
                (d[0], d[1] - 5), font, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
    str_down = 'COUNT:' + str(cnt_down+1)
    cv2.line(frame, (0, line_down),
             (int(frame.shape[1]), line_down), (255, 0, 0), 2)
    cv2.putText(frame, str_down, (10, 70), font,
                2.5, (0, 0, 0), 10, cv2.LINE_AA)
    cv2.putText(frame, str_down, (10, 70), font,
                2.5, (255, 255, 255), 8, cv2.LINE_AA)

    save_image_name += '_{0:03d}.jpg'.format(cnt_down)
    save_image_name = os.path.join(os.getcwd(), save_image_name)
    ret = cv2.imwrite('test.jpg', frame)


def convert_to_latlng(lat, lng):
    lat = lat.split('.')
    lng = lng.split('.')
    lat[2] = lat[2][:2] + '.' + lat[2][2]
    lng[2] = lng[2][:2] + '.' + lng[2][2]
    print(lat[2])
    print(lng[2])

    lat = (float(lat[2])/3600) + (int(lat[1]) / 60) + int(lat[0])
    lng = (float(lng[2])/3600) + (int(lng[1]) / 60) + int(lng[0])
    return lat, lng
