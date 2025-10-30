from typing import Any
from fastapi.responses import JSONResponse

class HttpResponse:
   # BASE METHOD
    @staticmethod
    def custom(message: str, response: Any = None, status_code: int = 200, error: Any = None):
        return JSONResponse(
            status_code=status_code,
            content={
                "message": message,
                "response": response,
                "statusCode": status_code,
                "error": error,
            },
        )

    # SUCCESS RESPONSES
    @staticmethod
    def success(message: str = "Success", response: Any = None):
        return HttpResponse.custom(message, response, 200)

    @staticmethod
    def created(response: Any = None):
        return HttpResponse.custom("Created successfully", response, 201)

    @staticmethod
    def updated(response: Any = None):
        return HttpResponse.custom("Updated successfully", response, 200)

    @staticmethod
    def deleted():
        return HttpResponse.custom("Deleted successfully", None, 200)

    @staticmethod
    def no_content():
        return HttpResponse.custom("No Content", None, 204)

    # ERROR RESPONSES

    @staticmethod
    def bad_request(error: Any = None):
        return HttpResponse.custom("Bad Request", None, 400, error)

    @staticmethod
    def unauthorized(error: Any = None):
        return HttpResponse.custom("Unauthorized", None, 401, error)

    @staticmethod
    def forbidden(error: Any = None):
        return HttpResponse.custom("Forbidden", None, 403, error)

    @staticmethod
    def not_found(error: Any = None):
        return HttpResponse.custom("Not Found", None, 404, error)

    @staticmethod
    def conflict(error: Any = None):
        return HttpResponse.custom("Conflict", None, 409, error)

    @staticmethod
    def unprocessable_entity(error: Any = None):
        return HttpResponse.custom("Unprocessable Entity", None, 422, error)

    @staticmethod
    def internal_server_error(error: Any = None):
        return HttpResponse.custom("Internal Server Error", None, 500, error)
