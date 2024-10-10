class WebsiteShutdownError(Exception):
    def __init__(self, msg='웹 사이트가 일시 정지 되었습니다. 잠시 후 다시 시도해주세요'):
        self.msg = msg

    def __str__(self):
        return self.msg

class BadDataError(Exception):
    def __init__(self, msg='네트워크, 또는 예외적인 페이지 이동으로 인해 정상적으로 데이터가 로딩되지 못했습니다'):
        self.msg = msg

    def __str__(self):
        return self.msg
    
class LoginError(Exception):
    def __init__(self, msg='로그인에 실패하였습니다'):
        self.msg = msg

    def __str__(self):
        return self.msg
    
class ElementDeleteFailedError(Exception):
    def __init__(self, msg='상품 삭제에 실패했습니다'):
        self.msg = msg

    def __str__(self):
        return self.msg
    
