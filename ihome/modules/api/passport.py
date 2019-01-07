# 获取图片验证码

import random
import re
from datetime import datetime

from flask import request, abort, current_app, make_response, Response, jsonify, session

from ihome import sr, db
from ihome.libs.captcha.pic_captcha import captcha
from ihome.models import User
from ihome.modules.api import api_blu
from ihome.utils.constants import IMAGE_CODE_REDIS_EXPIRES, SMS_CODE_REDIS_EXPIRES

from ihome.utils.response_code import RET, error_map


# 获取图片验证码
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
            sr.delete("image_code_id" + pre)

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


# 注册
@api_blu.route("/user", methods=["POST"])
def user():
    # 获取参数
    phonecode = request.json.get("phonecode")
    mobile = request.json.get("mobile")
    password = request.json.get("password")
    # 校验参数
    # print(sms_code,mobile,password)
    if not all([phonecode, mobile, password]):
        return jsonify(errno=RET.PARAMERR, errmsg=error_map[RET.PARAMERR])
    # 手机号校验
    if not re.match(r"1[345678]\d{9}$", mobile):
        # print("手机校验失败")
        return jsonify(errno=RET.PARAMERR, errmsg=error_map[RET.PARAMERR])
    # 判断用户是否一存在
    try:
        user = User.query.filter(User.mobile == mobile).first()
    except BaseException as  e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg=error_map[RET.DBERR])

    if user:
        return jsonify(errno=RET.DATAEXIST, errmsg=error_map[RET.DATAEXIST])
    # 校验短信验证码，更具手机号取出短信验证码
    # print("手机校验通过了")
    try:
        real_phonecode = sr.get("sms_code_id" + mobile)
    except BaseException as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg=error_map[RET.DBERR])
    # 如获取到了验证码
    if real_phonecode != phonecode:
        # print("验证码错误")
        return jsonify(errno=RET.PARAMERR, errmsg=error_map[RET.PARAMERR])

    # 记录用户数据
    user = User()
    user.mobile = mobile
    user.name = mobile
    # user.password_hash=password   #  直接存储密码为明文密码  不安全

    # 使用计算属性封装密码
    user.password = password
    db.session.add(user)

    try:
        db.session.commit()
    except BaseException as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg=error_map[RET.DBERR])

    # 使用session 记录用户登录状态，记录主键就可以查询出其他的数据
    session["user_id"] = user.id

    # json 返回结果
    return jsonify(errno=RET.OK, errmsg=error_map[RET.OK])


# 登录
@api_blu.route("/session", methods=["POST"])
def login():
    # 获取参数
    mobile = request.json.get("mobile")
    password = request.json.get("password")
    # 校验参数
    if not all([mobile, password]):
        return jsonify(errno=RET.PARAMERR, errmsg=error_map[RET.PARAMERR])

    # 取出用户数据
    try:
        user = User.query.filter_by(mobile=mobile).first()
    except BaseException as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg=error_map[RET.DBERR])

    # 判断用户是否存在
    if not user:
        return jsonify(errno=RET.USERERR, errmsg=error_map[RET.USERERR])

    # 校验密码
    if not user.check_password(password):
        return jsonify(errno=RET.PWDERR, errmsg=error_map[RET.PWDERR])

    # 使用session记录用户登录状态 记录主键就可以查询出其他的数据
    sr.set("user_id",user.id)

    # json返回数据
    return jsonify(errno=RET.OK, errmsg=error_map[RET.OK])


# 获取登录数据
@api_blu.route("/session")
def session():
    # 获取参数
    user_id = sr.get("user_id")

    if not user_id:
        return jsonify(errno=RET.SESSIONERR, errmsg=error_map[RET.SESSIONERR])

    try:
        user = User.query.get(user_id)
    except BaseException as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg=error_map[RET.DBERR])

    data = {
        "name": user.name,
        "user_id": user_id
    }
    return jsonify(errno=RET.OK, errmsg=error_map[RET.OK], data=data)
