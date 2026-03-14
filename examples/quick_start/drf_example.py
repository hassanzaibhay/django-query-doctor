"""
DRF integration — how to optimize serializers flagged by query-doctor.
"""

# BEFORE (what query-doctor flags):
# ----------------------------------
# from rest_framework import serializers, viewsets
#
# class BookSerializer(serializers.ModelSerializer):
#     author_name = serializers.CharField(source="author.name")   # N+1!
#     publisher = serializers.CharField(source="publisher.name")   # N+1!
#
#     class Meta:
#         model = Book
#         fields = ["id", "title", "author_name", "publisher", "price"]
#
# class BookViewSet(viewsets.ReadOnlyModelViewSet):
#     serializer_class = BookSerializer
#     queryset = Book.objects.all()  # No optimization — query-doctor flags this


# AFTER (the fix query-doctor prescribes):
# -----------------------------------------
# class BookViewSet(viewsets.ReadOnlyModelViewSet):
#     serializer_class = BookSerializer
#     queryset = Book.objects.select_related("author", "publisher").all()
#     # That's it. N+1 gone. Query-doctor confirms: 0 issues.
