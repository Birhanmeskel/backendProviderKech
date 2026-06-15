from rest_framework import serializers

from apps.payments.models import Payment


class PaymentInitSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()


class PaymentVerifySerializer(serializers.Serializer):
    order_id = serializers.IntegerField(required=False)
    tx_ref = serializers.CharField(required=False, max_length=128)

    def validate(self, attrs):
        if not attrs.get("order_id") and not attrs.get("tx_ref"):
            raise serializers.ValidationError("Provide order_id or tx_ref.")
        return attrs


class PaymentSerializer(serializers.ModelSerializer):
    order_reference = serializers.CharField(source="order.reference", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    # Avoid URL validation failures when checkout_url is blank in DB.
    checkout_url = serializers.CharField(read_only=True, allow_blank=True)

    class Meta:
        model = Payment
        fields = (
            "id",
            "order",
            "order_reference",
            "customer",
            "customer_phone",
            "amount",
            "currency",
            "chapa_tx_ref",
            "chapa_reference",
            "payment_method",
            "status",
            "checkout_url",
            "paid_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class PaymentInitResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ("id", "order", "chapa_tx_ref", "checkout_url", "amount", "currency", "status")
