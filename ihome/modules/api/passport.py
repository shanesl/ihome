# 获取图片验证码
import random

from flask import request, abort, current_app, make_response, Response, jsonify

from ihome import sr
from ihome.libs.captcha.pic_captcha import captcha
from ihome.models import User
from ihome.modules.api import api_blu
from ihome.utils.constants import IMAGE_CODE_REDIS_EXPIRES, SMS_CODE_REDIS_EXPIRES

# 获取图片验证码
from ihome.utils.response_code import RET, error_map


@api_blu.route("/imagecode")
def get_img_code():
    # 获取参数
    cur = request.args.get("cur")  # 验证码编号
    pre = request.args.get("pre")  # 上次验证码编号
    # 参数校验
    if not cur:
        return abort(403)  # 403 表示服务器拒绝访问

    # 生成图片验证码(图片+文字)
    img_name, img_text, img_bytes = captcha.generate_captcha()

    # 保存验证码文字和图片key redis 方便设置过期时间，性能也好，键值关系满足需求
    try:
        if pre:
            sr.delete("image_code_id"+pre)

        sr.set("image_code_id" + cur, img_text, ex=IMAGE_CODE_REDIS_EXPIRES)
    except BaseException as e:
        current_app.logger.error(e)  # 记录错误信息
        return abort(500)  # (服务器内部错误)服务器遇到错误，无法完成请求
    # 返回图片 自定义响应对象

    response = make_response(img_bytes)  # type:Response
    # 设置响应头
    response.content_type = "image/jpeg"
    return response


# 获取短信验证码
# 获取短信验证码
@api_blu.route("/smscode", methods=["POST"])
def get_sms_code():
    # 获取参数
    image_code_id = request.json.get("image_code_id")
    image_code = request.json.get("image_code")
    mobile = request.json.get("mobile")
    # 校验参数
    print(image_code_id, image_code, mobile)
    if not all([image_code_id, image_code, mobile]):
        return jsonify(errno=RET.PARAMERR, errmsg=error_map[RET.PARAMERR])

    # 根据图片key取出验证码文字
    try:
        real_img_code = sr.get("image_code_id" + image_code_id)
    except BaseException as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg=error_map[RET.DBERR])

    print("实际验证码：", real_img_code)
    print("获取到的验证码", image_code)
    # 校验图片验证码（文字）
    if real_img_code != image_code.upper():
        return jsonify(errno=RET.PARAMERR, errmsg=error_map[RET.PARAMERR])

    # 获取短信验证码 细节处理
    # 用户存在则不需要重新注册
    # 判断用户是否存在
    try:
        user = User.query.filter_by(mobile=mobile).first()
    except BaseException as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg=error_map[RET.DBERR])

    if user:
        return jsonify(errno=RET.DATAEXIST, errmsg=error_map[RET.DATAEXIST])

    # 生成随机短信验证码
    rand_num = "%04d" % random.randint(0, 9999)  # 4位随机数

    # # 发送短信
    # response_code = CCP().send_template_sms(mobile, [rand_num, 5], 1)
    # if response_code != 0:  # 发送失败
    #     return jsonify(RET.THIRDERR, errmsg=error_map[RET.THIRDERR])

    # 保存短信
    try:
        sr.set("sms_code_id" + mobile, rand_num, ex=SMS_CODE_REDIS_EXPIRES)
    except BaseException as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg=error_map[RET.DBERR])

    # 控制台打印短信验证码
    current_app.logger.info("短信验证码位：%s" % rand_num)

    # json 返回发送结果
    return jsonify(errno=RET.OK, errmsg=error_map[RET.OK])

