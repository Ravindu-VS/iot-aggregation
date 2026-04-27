
class BackendError(Exception):
    
    def __init__(self, message: str = "An unexpected backend error occurred"):
        self.message = message
        super().__init__(self.message)


class ValidationError(BackendError):
   

    def __init__(self, message: str = "Payload validation failed"):
        super().__init__(message)


class RecordNotFoundError(BackendError):
   

    def __init__(self, data_id: str):
        self.data_id = data_id
        super().__init__(f"Record not found: {data_id}")
