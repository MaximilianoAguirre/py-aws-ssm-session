def iterate_boto3_request(boto3_request, field, **kargs):
    request = boto3_request(**kargs)
    response = request[field]
    next = request.get("NextToken")

    while next:
        request = boto3_request(NextToken=next, **kargs)
        response += request[field]
        next = request.get("NextToken")

    return response
