class ServiceError(Exception):
    pass


class ContactNotFoundError(ServiceError):
    pass


class CommunicationNotFoundError(ServiceError):
    pass


class ContactAlreadyExistsError(ServiceError):
    pass
