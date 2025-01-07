from django.core.exceptions import ValidationError


def validate_file_size(max_file_size: int):
    def inner(file_obj):
        filesize = file_obj.size
        if filesize > max_file_size:
            raise ValidationError("Max file size is %s MB" % str(max_file_size))
