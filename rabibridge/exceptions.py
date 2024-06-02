class RemoteExecutionError(Exception):
    '''
    Raised when an exception occurs during remote execution.
    '''
    pass

class FileChangedException(Exception):
    '''
    Raised when the file has been changed.
    '''
    pass