from datetime import timedelta
from decimal import Decimal
from random import choices

from django.utils import timezone

from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from .money import CURRENCY_CHOICES, CURRENCY_UZS, CURRENCY_USD, format_money

class Viloyat(models.Model):
    name = models.CharField('Nomi', max_length=120, unique=True)
    is_active = models.BooleanField('Faol', default=True)

    class Meta:
        verbose_name = 'Viloyat'
        verbose_name_plural = 'Viloyatlar'
        ordering = ['name']

    def __str__(self):
        return self.name

class District(models.Model):

    KIND_CHOICES = (
        ('tuman', 'Tuman'),
        ('shahar', 'Shahar'),
    )
    viloyat = models.ForeignKey(
        Viloyat, on_delete=models.CASCADE, related_name='districts', verbose_name='Viloyat'
    )
    name = models.CharField('Nomi', max_length=120)
    kind = models.CharField('Turi', max_length=20, choices=KIND_CHOICES, default='tuman')
    is_active = models.BooleanField('Faol', default=True)

    class Meta:
        verbose_name = 'Tuman / shahar'
        verbose_name_plural = 'Tuman / shaharlar'
        ordering = ['viloyat__name', 'name']
        unique_together = (('viloyat', 'name'),)

    def __str__(self):
        return f"{self.name} ({self.viloyat.name})"

class Organization(models.Model):

    district = models.ForeignKey(
        District,
        on_delete=models.PROTECT,
        related_name='organizations',
        null=True,
        blank=True,
        verbose_name='Tuman / shahar',
    )
    name = models.CharField('Nomi', max_length=200, help_text='Tashkilotning to‘liq nomi')
    brand_name = models.CharField('Brend', max_length=100, default='Tezkor', help_text='Qisqa brend nomi')
    logo = models.ImageField('Logo', upload_to='branding/', null=True, blank=True)
    phone = models.CharField('Telefon', max_length=50, blank=True)
    address = models.CharField('Manzil', max_length=255, blank=True)
    is_active = models.BooleanField('Faol', default=True)

    class Meta:
        verbose_name = 'Tashkilot'
        verbose_name_plural = 'Tashkilotlar'

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):

        self.is_active = False
        self.save(update_fields=['is_active'])
        self.branches.filter(is_active=True).update(is_active=False)

    @classmethod
    def get_default(cls):
        org = cls.objects.filter(is_active=True).order_by('id').first()
        if org:
            return org
        return cls.objects.create(name='Tezkor Savdo', brand_name='Tezkor')

class Branch(models.Model):
    organization = models.ForeignKey(
        'Organization',
        on_delete=models.PROTECT,
        related_name='branches',
        null=True,
        blank=True,
        verbose_name='Tashkilot',
    )
    name = models.CharField('Nomi', max_length=100)
    address = models.CharField('Manzil', max_length=100, blank=True)
    phone_number = models.CharField('Telefon', max_length=100, blank=True)
    is_active = models.BooleanField('Faol', default=True)

    class Meta:
        verbose_name = 'Filial'
        verbose_name_plural = 'Filiallar'

    def delete(self, *args, **kwargs):
        self.is_active = False
        self.save()

    @property
    def organization_name(self):
        if self.organization_id:
            return self.organization.name
        return Organization.get_default().name

    def __str__(self):
        status = '' if self.is_active else ' (Faol emas)'
        if self.organization_id:
            return f"{self.name} · {self.organization.brand_name or self.organization.name}{status}"
        return f"{self.name}{status}"

class StaffAccess(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='staff_access',
        verbose_name='Foydalanuvchi',
    )
    viloyats = models.ManyToManyField(
        Viloyat,
        blank=True,
        related_name='staff_users',
        verbose_name='Viloyatlar',
    )
    districts = models.ManyToManyField(
        District,
        blank=True,
        related_name='staff_users',
        verbose_name='Tuman / shaharlar',
    )
    organizations = models.ManyToManyField(
        Organization,
        blank=True,
        related_name='staff_users',
        verbose_name='Tashkilotlar',
    )
    branches = models.ManyToManyField(
        Branch,
        blank=True,
        related_name='staff_users',
        verbose_name='Filiallar',
    )

    class Meta:
        verbose_name = 'Admin hudud ruxsati'
        verbose_name_plural = 'Admin hudud ruxsatlari'

    def __str__(self):
        return f"{self.user.username} — hudud ruxsati"

class PriceTier(models.Model):

    KIND_REGULAR = 'regular'
    KIND_LOYAL = 'loyal'
    KIND_PARTNER = 'partner'
    SYSTEM_KINDS = (KIND_REGULAR, KIND_LOYAL, KIND_PARTNER)
    KIND_LABELS = {
        KIND_REGULAR: 'Oddiy',
        KIND_LOYAL: 'Sodiq',
        KIND_PARTNER: 'Hamkor',
    }
    KIND_CHOICES = (
        (KIND_REGULAR, 'Oddiy'),
        (KIND_LOYAL, 'Sodiq'),
        (KIND_PARTNER, 'Hamkor'),
    )
    kind = models.SlugField('Tur', max_length=32, unique=True, default=KIND_REGULAR, db_index=True)
    code = models.SlugField('Kod', max_length=32, unique=True)
    name = models.CharField('Nomi', max_length=80)
    discount_percent = models.DecimalField(
        'Chegirma %', max_digits=5, decimal_places=2, default=Decimal('0.00'),
        help_text='Masalan 5 = 5% arzon',
    )
    is_active = models.BooleanField('Faol', default=True)

    class Meta:
        verbose_name = 'Narx darajasi'
        verbose_name_plural = 'Narx darajalari'
        ordering = ['discount_percent', 'name']

    def __str__(self):
        return f"{self.name} (−{self.discount_percent}%)"

    def get_kind_display(self):
        return self.KIND_LABELS.get(self.kind, self.name or self.kind)

    @property
    def is_system(self):
        return self.kind in self.SYSTEM_KINDS

    def save(self, *args, **kwargs):
        if self.kind:
            self.code = self.kind
        super().save(*args, **kwargs)

    @classmethod
    def discount_tiers(cls):
        return cls.objects.exclude(kind=cls.KIND_REGULAR).filter(is_active=True).order_by('kind')

    @classmethod
    def discount_type_choices(cls):
        return [(t.kind, t.name) for t in cls.discount_tiers()]

class Customer(models.Model):
    TYPE_REGULAR = 'regular'
    TYPE_LOYAL = 'loyal'
    TYPE_PARTNER = 'partner'
    TYPE_CHOICES = (
        (TYPE_REGULAR, 'Oddiy mijoz'),
        (TYPE_LOYAL, 'Sodiq mijoz'),
        (TYPE_PARTNER, 'Hamkor / Usta'),
    )

    name = models.CharField('Ism', max_length=100)
    email = models.EmailField('Email', max_length=100, blank=True)
    address = models.CharField('Manzil', max_length=100, blank=True)
    phone = models.CharField('Telefon', max_length=100, blank=True)
    customer_type = models.CharField(
        'Turi', max_length=32, default=TYPE_REGULAR, db_index=True,
    )
    price_tier = models.ForeignKey(
        PriceTier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customers',
        verbose_name='Narx darajasi',
    )
    bonus_discount_percent = models.DecimalField(
        'Shaxsiy aksiya %',
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Tur chegirmasidan yuqori bo‘lsa, kassada shu foiz qo‘llanadi',
    )
    notes = models.CharField('Izoh', max_length=255, blank=True)
    date_created = models.DateField('Yaratilgan sana', auto_now_add=True)
    is_active = models.BooleanField('Faol', default=True)

    class Meta:
        verbose_name = 'Mijoz'
        verbose_name_plural = 'Mijozlar'

    def __str__(self):
        return f"{self.name} {'(Faol emas)' if not self.is_active else ''}"

    def get_customer_type_display(self):
        if self.price_tier_id and self.price_tier:
            return self.price_tier.name
        tier = PriceTier.objects.filter(kind=self.customer_type).first()
        if tier:
            return tier.name
        return dict(self.TYPE_CHOICES).get(self.customer_type, self.customer_type)

    def get_tier_discount_percent(self):
        if self.price_tier_id and self.price_tier and self.price_tier.is_active:
            return self.price_tier.discount_percent or Decimal('0.00')
        tier = PriceTier.objects.filter(code=self.customer_type, is_active=True).first()
        if tier:
            return tier.discount_percent or Decimal('0.00')
        return Decimal('0.00')

    def get_discount_percent(self):
        tier_pct = self.get_tier_discount_percent()
        bonus = self.bonus_discount_percent or Decimal('0.00')
        return max(tier_pct, bonus)

    def save(self, *args, **kwargs):
        if not self.price_tier_id and self.customer_type:
            tier = PriceTier.objects.filter(code=self.customer_type, is_active=True).first()
            if tier:
                self.price_tier = tier
        super().save(*args, **kwargs)

class Employee(models.Model):
    ROLE_CHOICES = (
        ('Sales Agent', 'Sotuvchi'),
        ('Consultant', 'Maslahatchi'),
        ('Manager', 'Menejer'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name='Foydalanuvchi')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, verbose_name='Filial')
    name = models.CharField('Ism', max_length=100)
    role = models.CharField('Lavozim', choices=ROLE_CHOICES, max_length=100, default='Sales Agent')
    email = models.EmailField('Email', max_length=200, null=True, blank=True)
    phone = models.CharField('Telefon', max_length=20, null=True, blank=True)
    profile_pic = models.ImageField('Profil rasmi', upload_to='profiles/', null=True, blank=True)
    hire_date = models.DateField('Ishga olingan sana', auto_now_add=True)
    is_active = models.BooleanField('Faol', default=True)
    is_logged_in = models.BooleanField('Tizimda', default=False)
    last_login_time = models.DateTimeField('Oxirgi kirish', null=True, blank=True)
    last_logout_time = models.DateTimeField('Oxirgi chiqish', null=True, blank=True)

    class Meta:
        verbose_name = 'Xodim'
        verbose_name_plural = 'Xodimlar'

    def __str__(self):
        return f"{self.name}{'' if self.is_active else ' (Faol emas)'}"

    def save(self, *args, **kwargs):
        if not self.is_active and self.user.is_active:
            self.user.is_active = False
            self.user.save()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self.is_active = False
        self.save()

class SalesAgent(models.Model):
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, limit_choices_to={'is_active': True}, verbose_name='Xodim')
    commission_rate = models.DecimalField('Komissiya foizi', max_digits=5, decimal_places=2, default=0.00)
    total_commission_earned = models.DecimalField('Jami komissiya', max_digits=12, decimal_places=2, default=0.00)
    total_sales = models.DecimalField('Jami savdo', max_digits=12, decimal_places=2, default=0.00)

    class Meta:
        verbose_name = 'Sotuvchi'
        verbose_name_plural = 'Sotuvchilar'

    def __str__(self):
        return f"Sotuvchi: {self.employee.name}"

class Supplier(models.Model):
    OPTION = (
    ('Renewed', 'Yangilangan'),
    ('Opted Out', 'Bekor qilingan'),
    ('Active', 'Faol'),
    ('Expired', 'Muddati tugagan')
    )

    name = models.CharField('Nomi', max_length=100)
    contact_person = models.CharField('Aloqa shaxsi', max_length=100, blank=True)
    phone = models.CharField('Telefon', max_length=100, blank=True)
    contract_expiration = models.DateField('Shartnoma tugashi')
    contract_start = models.DateField('Shartnoma boshlanishi', auto_now_add=True)
    status = models.CharField('Holat', choices=OPTION, max_length=100, default='Active')
    is_active = models.BooleanField('Faol', default=True)

    class Meta:
        verbose_name = 'Yetkazib beruvchi'
        verbose_name_plural = 'Yetkazib beruvchilar'

    def soft_delete(self):
        self.is_active = False
        self.save()

    @property
    def contract_status(self):
        today = timezone.now().date()

        if today > self.contract_expiration:
            return 'Muddati tugagan'
        else:
            return self.get_status_display()

    @property
    def contract_period(self):
        if not self.contract_start or not self.contract_expiration:
            return 'Mavjud emas'

        start = self.contract_start.year
        end = self.contract_expiration.year

        if start == end:
            return f"{start}"
        return f"{start} - {end}"

    def __str__(self):
        return f"{self.name} {'(Arxivlangan)' if not self.is_active else ''}"

class ProductCategory(models.Model):
    name = models.CharField('Nomi', max_length=100, unique=True)
    is_active = models.BooleanField('Faol', default=True)
    created_at = models.DateTimeField('Yaratilgan', auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Kategoriya'
        verbose_name_plural = 'Kategoriyalar'

    def __str__(self):
        return self.name

class AppSettings(models.Model):

    usd_to_uzs = models.DecimalField(
        '1 USD = so‘m',
        max_digits=14,
        decimal_places=2,
        default=12500,
        help_text='Ombor kirimida dollar ↔ so‘m konvertatsiya kursi',
    )
    vat_enabled = models.BooleanField(
        'QQS yoqilgan',
        default=True,
        help_text='Kassada QQS qo‘shilsinmi',
    )
    vat_percent = models.DecimalField(
        'QQS foizi',
        max_digits=5,
        decimal_places=2,
        default=12,
        help_text='Masalan 12 = 12%',
    )
    pos_secret_code = models.CharField(
        'Kassa maxfiy kodi',
        max_length=32,
        blank=True,
        default='9090',
        help_text='Kassada «Qabul qilingan naqd» maydoniga shu kod yozilsa chegirma qo‘llanadi',
    )
    pos_secret_discount_percent = models.DecimalField(
        'Maxfiy kod chegirmasi %',
        max_digits=5,
        decimal_places=2,
        default=10,
        help_text='Maxfiy kod kiritilganda umumiy summadan chegirma foizi',
    )
    pos_secret_markup_code = models.CharField(
        'Kassa maxfiy ustama kodi',
        max_length=32,
        blank=True,
        default='',
        help_text='Kassada «Qabul qilingan naqd» maydoniga shu kod yozilsa ustama qo‘llanadi',
    )
    pos_secret_markup_percent = models.DecimalField(
        'Maxfiy kod ustamasi %',
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text='Ustama kodi kiritilganda umumiy summaga qo‘shiladigan foiz',
    )
    THEME_SYSTEM = 'system'
    THEME_DAY = 'day'
    THEME_NIGHT = 'night'
    THEME_AUTO = 'auto'
    THEME_MODE_CHOICES = (
        (THEME_SYSTEM, 'Tizim bilan'),
        (THEME_DAY, 'Kunduz'),
        (THEME_NIGHT, 'Qorong‘u'),
        (THEME_AUTO, 'Soat bo‘yicha'),
    )
    theme_mode = models.CharField(
        'Interfeys rejimi',
        max_length=10,
        choices=THEME_MODE_CHOICES,
        default=THEME_SYSTEM,
    )
    theme_day_start = models.PositiveSmallIntegerField(
        'Kunduz boshlanishi (soat)',
        default=6,
        help_text='0–23, faqat «Soat bo‘yicha» rejimida',
    )
    theme_night_start = models.PositiveSmallIntegerField(
        'Kecha boshlanishi (soat)',
        default=19,
        help_text='0–23, faqat «Soat bo‘yicha» rejimida',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Tizim sozlamasi'
        verbose_name_plural = 'Tizim sozlamalari'

    def __str__(self):
        return f"1 USD = {self.usd_to_uzs} so‘m · QQS {self.vat_percent}%"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def vat_factor(self):

        if not self.vat_enabled:
            return Decimal('1')
        rate = self.vat_percent or Decimal('0')
        return (Decimal('1') + (rate / Decimal('100'))).quantize(Decimal('0.0001'))

class Product(models.Model):

    CATEGORIES = (
        ('Laptop', 'Noutbuk'),
        ('Android', 'Android'),
        ('iPhone', 'iPhone'),
        ('Printer', 'Printer'),
    )

    UNIT_TA = 'ta'
    UNIT_M = 'm'
    UNIT_KG = 'kg'
    UNIT_L = 'l'
    UNIT_M2 = 'm2'
    UNIT_QUTI = 'quti'
    UNIT_JUFT = 'juft'
    UNIT_CHOICES = (
        (UNIT_TA, 'ta (dona)'),
        (UNIT_M, 'm (metr)'),
        (UNIT_KG, 'kg'),
        (UNIT_L, 'l (litr)'),
        (UNIT_M2, 'm²'),
        (UNIT_QUTI, 'quti'),
        (UNIT_JUFT, 'juft'),
    )
    # Kasrli miqdorga ruxsat beriladigan birliklar
    FRACTIONAL_UNITS = {UNIT_M, UNIT_KG, UNIT_L, UNIT_M2}

    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, verbose_name='Yetkazib beruvchi')
    product_name = models.CharField('Mahsulot nomi', max_length=100)
    category = models.CharField('Kategoriya', max_length=100, default='Noutbuk')
    unit = models.CharField(
        'O‘lchov birligi',
        max_length=10,
        choices=UNIT_CHOICES,
        default=UNIT_TA,
        help_text='ta, m, kg va h.k. — savatda miqdor shu birlikda',
    )
    currency = models.CharField(
        'Sotish valyutasi',
        max_length=3,
        choices=CURRENCY_CHOICES,
        default=CURRENCY_UZS,
        help_text='Sotish narxi shu valyutada saqlanadi',
    )
    base_price = models.DecimalField('Sotish narxi', max_digits=14, decimal_places=2)
    sale_discount_percent = models.DecimalField(
        'Skidka %',
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Mahsulotga beriladigan chegirma foizi (0–100)',
    )
    sale_active = models.BooleanField(
        'Skidka faol',
        default=False,
        help_text='Yoqilganda kassada chegirmali narx ko‘rinadi',
    )
    sale_starts_at = models.DateField('Skidka boshlanishi', null=True, blank=True)
    sale_ends_at = models.DateField('Skidka tugashi', null=True, blank=True)
    barcode = models.CharField('Shtrixkod', max_length=100, unique=True)
    cost_currency = models.CharField(
        'Tannarx valyutasi',
        max_length=3,
        choices=CURRENCY_CHOICES,
        default=CURRENCY_USD,
        help_text='Tannarx odatda dollarda saqlanadi',
    )
    cost_price = models.DecimalField('Tannarx', max_digits=14, decimal_places=2)
    min_stock_level = models.DecimalField('Minimal zaxira', max_digits=12, decimal_places=3, default=Decimal('3'))
    warranty_days = models.PositiveIntegerField(
        'Mahsulot kafolati (kun)',
        default=365,
        help_text='Sotib olishdan keyin ta’mirlash uchun kafolat muddati',
    )
    replacement_days = models.PositiveIntegerField(
        'Almashtirish muddati (kun)',
        default=7,
        help_text='Sotib olishdan keyin almashtirish uchun muddat',
    )
    service_warranty_days = models.PositiveIntegerField(
        'Ish/xizmat kafolati (kun)',
        default=90,
        help_text='Ta’mirlash/xizmatdan keyin qo‘shimcha kafolat muddati',
    )
    image = models.ImageField('Rasm', upload_to='products/', null=True, blank=True)
    is_active = models.BooleanField('Faol', default=True)
    deleted_at = models.DateTimeField('O‘chirilgan vaqt', null=True, blank=True)

    class Meta:
        verbose_name = 'Mahsulot'
        verbose_name_plural = 'Mahsulotlar'

    def __str__(self):
        return f"{self.product_name} | {self.barcode}"

    def get_category_display(self):

        for key, label in self.CATEGORIES:
            if self.category == key:
                return label
        return self.category or '—'

    def allows_fractional_qty(self):
        return (self.unit or self.UNIT_TA) in self.FRACTIONAL_UNITS

    def unit_label(self):
        return dict(self.UNIT_CHOICES).get(self.unit, self.unit or 'ta')

    def soft_delete(self):
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save()

    def is_sale_active(self):
        pct = self.sale_discount_percent or Decimal('0')
        if not self.sale_active or pct <= 0:
            return False
        today = timezone.localdate()
        if self.sale_starts_at and today < self.sale_starts_at:
            return False
        if self.sale_ends_at and today > self.sale_ends_at:
            return False
        return True

    def get_sale_discount_percent(self):
        if not self.is_sale_active():
            return Decimal('0.00')
        pct = self.sale_discount_percent or Decimal('0.00')
        if pct < 0:
            return Decimal('0.00')
        if pct > Decimal('100'):
            return Decimal('100.00')
        return pct

    def get_effective_price(self):
        """Kassada sotiladigan narx (skidka bo‘lsa — chegirmadan keyin)."""
        from .loyalty import apply_discount
        base = self.base_price or Decimal('0.00')
        pct = self.get_sale_discount_percent()
        if pct > 0:
            return apply_discount(base, pct)
        return base

class BranchInventory(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, limit_choices_to={'is_active': True}, verbose_name='Filial')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name='Mahsulot')
    quantity = models.DecimalField('Miqdor', max_digits=12, decimal_places=3, default=Decimal('0'))
    date_added = models.DateTimeField('Qo‘shilgan sana', auto_now_add=True)

    class Meta:
        ordering = ['-date_added']
        verbose_name = 'Filial ombori'
        verbose_name_plural = 'Filial omborlari'

    def __str__(self):
        return f"{self.branch} | {self.product} | {self.quantity}"

class Order(models.Model):
    ORDER_STATUS = (
        ('AwaitingApproval', 'Tasdiqlash kutilmoqda'),
        ('Pending', 'Kutilmoqda'),
        ('Completed', 'Yakunlangan'),
        ('Returned', 'Qaytarilgan'),
        ('Cancelled', 'Bekor qilingan'),
    )

    PAYMENT_METHOD = (
    ('CASH', 'Naqd'),
    )

    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, limit_choices_to={'is_active': True}, verbose_name='Mijoz')
    partner = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='referred_orders',
        limit_choices_to={'is_active': True, 'customer_type': 'partner'},
        verbose_name='Hamkor / usta',
        help_text='Mijozni olib kelgan usta yoki hamkor',
    )
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name='Xodim')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, verbose_name='Filial')

    order_date = models.DateTimeField('Buyurtma sanasi', auto_now_add=True)
    total_amount = models.DecimalField('Jami summa', max_digits=14, decimal_places=2, default=0.00)
    list_total = models.DecimalField('Chegirmasiz jami', max_digits=14, decimal_places=2, default=0.00)
    discount_percent = models.DecimalField('Chegirma %', max_digits=5, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField('Chegirma summa', max_digits=14, decimal_places=2, default=Decimal('0.00'))
    currency = models.CharField('Valyuta', max_length=3, choices=CURRENCY_CHOICES, default=CURRENCY_UZS)
    order_status = models.CharField('Holat', choices=ORDER_STATUS, max_length=100, default='Pending')
    payment_method = models.CharField('To‘lov usuli', choices=PAYMENT_METHOD, max_length=100)
    is_active = models.BooleanField('Faol', default=True)
    deleted_at = models.DateTimeField('O‘chirilgan vaqt', null=True, blank=True)

    class Meta:
        verbose_name = 'Buyurtma'
        verbose_name_plural = 'Buyurtmalar'

    def __str__(self):
        return f"{self.id} | {self.branch.name}"

    def soft_delete(self):
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save()

    def get_cash_received(self):

        payment = self.payment_set.order_by('id').first()
        if not payment:
            return None
        try:
            return payment.cashpayment.cash_received
        except Exception:
            return payment.amount_paid

    def get_change_given(self):
        payment = self.payment_set.order_by('id').first()
        if not payment:
            return Decimal('0.00')
        try:
            return payment.cashpayment.change_given or Decimal('0.00')
        except Exception:
            return Decimal('0.00')

    def get_primary_debt(self):

        debts = list(self.debts.all())
        if not debts:
            return None
        open_debts = [d for d in debts if d.status != 'Paid']
        return open_debts[0] if open_debts else debts[0]

    def payment_summary_label(self):
        if self.order_status == 'AwaitingApproval':
            return 'To‘lov yo‘q (kutilmoqda)'
        if self.order_status == 'Cancelled':
            return 'Bekor qilingan'
        if self.order_status == 'Returned':
            return 'To‘liq qaytarilgan'
        debt = self.get_primary_debt()
        if debt and debt.remaining_balance > 0:
            return 'Naqd + Qarz'
        if debt:
            return 'Naqd (qarz yopilgan)'
        if not self.payment_set.exists():
            return 'To‘lov yo‘q'
        return self.get_payment_method_display()

    def can_be_returned(self):
        if not self.is_active or self.deleted_at:
            return False
        if self.order_status in ('AwaitingApproval', 'Cancelled', 'Returned'):
            return False
        return any(item.returnable_quantity() > 0 for item in self.orderitem_set.all())

    def total_returned_amount(self):
        total = Decimal('0.00')
        for ret in self.returns.filter(status='Completed', is_active=True):
            total += ret.total_amount or Decimal('0.00')
        return total

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, limit_choices_to={'is_active': True}, verbose_name='Buyurtma')
    cost_price = models.DecimalField('Tannarx', max_digits=14, decimal_places=2)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name='Mahsulot')
    quantity = models.DecimalField('Miqdor', max_digits=12, decimal_places=3, default=Decimal('1'))
    list_unit_price = models.DecimalField('Asl birlik narxi', max_digits=14, decimal_places=2, default=0.00)
    unit_price = models.DecimalField('Birlik narxi', max_digits=14, decimal_places=2)
    discount_percent = models.DecimalField('Chegirma %', max_digits=5, decimal_places=2, default=Decimal('0.00'))
    price_adjusted = models.BooleanField(
        'Narx qo‘lda o‘zgartirilgan',
        default=False,
        help_text='Kassada bir martalik narx tahriri',
    )
    warranty_days = models.PositiveIntegerField('Mahsulot kafolati (kun)', default=365)
    replacement_days = models.PositiveIntegerField('Almashtirish muddati (kun)', default=7)
    service_warranty_days = models.PositiveIntegerField('Ish kafolati (kun)', default=90)

    class Meta:
        verbose_name = 'Buyurtma bandi'
        verbose_name_plural = 'Buyurtma bandlari'

    def __str__(self):
        return f"{self.quantity} | {self.product.product_name}"

    @property
    def line_total(self):
        return self.quantity * self.unit_price

    @property
    def list_line_total(self):
        price = self.list_unit_price if self.list_unit_price is not None else self.unit_price
        return self.quantity * price

    def effective_warranty_days(self):
        if self.warranty_days:
            return self.warranty_days
        return getattr(self.product, 'warranty_days', 365) or 365

    def effective_replacement_days(self):
        if self.replacement_days:
            return self.replacement_days
        return getattr(self.product, 'replacement_days', 7) or 7

    def effective_service_warranty_days(self):
        if self.service_warranty_days:
            return self.service_warranty_days
        return getattr(self.product, 'service_warranty_days', 90) or 90

    def returned_quantity(self):
        total = (
            self.return_items
            .filter(sale_return__status='Completed', sale_return__is_active=True)
            .aggregate(s=models.Sum('quantity'))
            .get('s')
        )
        return total or Decimal('0')

    def returnable_quantity(self):
        left = (self.quantity or Decimal('0')) - self.returned_quantity()
        return left if left > 0 else Decimal('0')

class Payment(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, limit_choices_to={'is_active': True}, verbose_name='Buyurtma')
    amount_paid = models.DecimalField('To‘langan summa', max_digits=10, decimal_places=2)
    date_paid = models.DateField('To‘lov sanasi')
    payment_type = models.CharField('To‘lov turi', max_length=100, choices=Order.PAYMENT_METHOD)

    class Meta:
        verbose_name = 'To‘lov'
        verbose_name_plural = 'To‘lovlar'

    def __str__(self):
        return f"Buyurtma{self.order.id} uchun to‘lov"

class CashPayment(models.Model):
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, verbose_name='To‘lov')
    cash_received = models.DecimalField('Qabul qilingan naqd', max_digits=10, decimal_places=2)
    change_given = models.DecimalField('Qaytim', max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = 'Naqd to‘lov'
        verbose_name_plural = 'Naqd to‘lovlar'

class Invoice(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='invoice', limit_choices_to={'is_active': True}, verbose_name='Buyurtma')
    or_number = models.CharField('Chek raqami', max_length=100, unique=True)
    invoice_date = models.DateField('Hisob-faktura sanasi')
    vat_amount = models.DecimalField('QQS', max_digits=10, decimal_places=2, default=0.00)
    grand_total = models.DecimalField('Umumiy jami', max_digits=10, decimal_places=2)
    issued_by = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name='Bergan xodim')

    class Meta:
        verbose_name = 'Hisob-faktura'
        verbose_name_plural = 'Hisob-fakturalar'

    def __str__(self):
        return f"Hisob-faktura {self.or_number}"

class WarrantyClaims(models.Model):
    CLAIM_TYPES = (
    ('Repair', 'Ta’mirlash'),
    ('Replacement', 'Almashtirish')
    )

    STATUS_CHOICES = (
    ('Pending', 'Kutilmoqda'),
    ('In-Progress', 'Jarayonda'),
    ('Completed', 'Yakunlangan'),
    ('Released', 'Berilgan'),
    )

    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name='warranty_claims', verbose_name='Buyurtma bandi')
    claim_type = models.CharField('Ariza turi', max_length=20, choices=CLAIM_TYPES, default='Repair')
    faulty_serial = models.CharField('Nuqsonli seriya', max_length=100)
    issue_description = models.TextField('Muammo tavsifi')
    status = models.CharField('Holat', max_length=20, choices=STATUS_CHOICES, default='Pending')
    date_filed = models.DateTimeField('Ariza sanasi', auto_now_add=True)
    resolution_date = models.DateTimeField('Yechilgan sana', null=True, blank=True)
    service_warranty_until = models.DateField(
        'Ish kafolati tugashi',
        null=True,
        blank=True,
        help_text='Ta’mirlash yakunlangandan keyin xizmat kafolati muddati',
    )
    cost_impact = models.DecimalField('Xarajat', max_digits=10, decimal_places=2, default=0.00, null=True, blank=True)
    handled_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, limit_choices_to={'is_active': True}, verbose_name='Mas’ul xodim')

    class Meta:
        verbose_name = 'Kafolat arizasi'
        verbose_name_plural = 'Kafolat arizalari'

    def __str__(self):
        return f"{self.get_claim_type_display()} arizasi - {self.order_item.product.product_name}"

    def activate_service_warranty(self):

        if self.claim_type != 'Repair':
            return
        days = self.order_item.effective_service_warranty_days()
        base = timezone.localdate()
        if self.resolution_date:
            base = timezone.localtime(self.resolution_date).date()
        self.service_warranty_until = base + timedelta(days=days)

class ReplacementRecord(models.Model):
    warranty_claims = models.OneToOneField(WarrantyClaims, on_delete=models.CASCADE, verbose_name='Kafolat arizasi')
    old_serial = models.CharField('Eski seriya', max_length=100)
    new_serial = models.CharField('Yangi seriya', max_length=100)
    replacement_date = models.DateTimeField('Almashtirish sanasi', auto_now_add=True)

    class Meta:
        verbose_name = 'Almashtirish yozuvi'
        verbose_name_plural = 'Almashtirish yozuvlari'

    def __str__(self):
        return f"Ariza #{self.warranty_claims.id} uchun almashtirish"

class DefectiveInventory(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name='Mahsulot')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, verbose_name='Filial')
    faulty_serial = models.CharField('Nuqsonli seriya', max_length=100)
    reason = models.TextField('Sabab')
    date_received = models.DateTimeField('Qabul qilingan sana', auto_now_add=True)
    is_disposed = models.BooleanField('Utilizatsiya qilingan', default=True)

    class Meta:
        verbose_name = 'Nuqsonli ombor'
        verbose_name_plural = 'Nuqsonli omborlar'

    def __str__(self):
        return f"Nuqsonli {self.product.product_name} - {self.faulty_serial}"

class AuditTrail(models.Model):
    ACTION_OPTIONS = [
        ('CREATE', 'Yaratish'),
        ('UPDATE', 'Yangilash'),
        ('DELETE', 'O‘chirish'),
    ]

    user = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Xodim')
    action = models.CharField('Amal', max_length=20, choices=ACTION_OPTIONS, default='CREATE')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, verbose_name='Ob’ekt turi')
    object_id = models.PositiveIntegerField('Ob’ekt ID')
    content_object = GenericForeignKey('content_type', 'object_id')
    change_log = models.JSONField('O‘zgarishlar', default=dict)
    ip_address = models.GenericIPAddressField('IP manzil', null=True)
    timestamp = models.DateTimeField('Vaqt', auto_now_add=True)

    class Meta:
        verbose_name = 'Audit yozuvi'
        verbose_name_plural = 'Audit jurnali'

class CustomerDebt(models.Model):
    STATUS_CHOICES = (
        ('Open', 'Ochiq'),
        ('Partial', 'Qisman'),
        ('Paid', 'To‘langan'),
    )

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name='debts', verbose_name='Mijoz'
    )
    order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='debts', verbose_name='Buyurtma'
    )
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, verbose_name='Filial')
    created_by = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_debts', verbose_name='Yaratgan'
    )
    currency = models.CharField('Valyuta', max_length=3, choices=CURRENCY_CHOICES, default=CURRENCY_UZS)
    original_amount = models.DecimalField('Dastlabki qarz', max_digits=14, decimal_places=2)
    paid_amount = models.DecimalField('To‘langan', max_digits=14, decimal_places=2, default=0)
    remaining_balance = models.DecimalField('Qolgan qarz', max_digits=14, decimal_places=2)
    status = models.CharField('Holat', max_length=20, choices=STATUS_CHOICES, default='Open')
    note = models.CharField('Izoh', max_length=255, blank=True)
    created_at = models.DateTimeField('Yaratilgan', auto_now_add=True)
    updated_at = models.DateTimeField('Yangilangan', auto_now=True)

    class Meta:
        verbose_name = 'Qarzdor'
        verbose_name_plural = 'Qarzdorlar'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.customer} — {self.remaining_balance} {self.currency}"

    def refresh_status(self):
        if self.remaining_balance <= 0:
            self.remaining_balance = Decimal('0.00')
            self.status = 'Paid'
        elif self.paid_amount > 0:
            self.status = 'Partial'
        else:
            self.status = 'Open'

class DebtPayment(models.Model):
    debt = models.ForeignKey(
        CustomerDebt, on_delete=models.CASCADE, related_name='payments', verbose_name='Qarz'
    )
    amount = models.DecimalField('Summa', max_digits=14, decimal_places=2)
    received_by = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Qabul qilgan'
    )
    paid_at = models.DateTimeField('To‘lov vaqti', auto_now_add=True)
    note = models.CharField('Izoh', max_length=255, blank=True)

    class Meta:
        verbose_name = 'Qarz to‘lovi'
        verbose_name_plural = 'Qarz to‘lovlari'
        ordering = ['-paid_at']

    def __str__(self):
        return f"Qarz #{self.debt_id}: {self.amount}"

class Expense(models.Model):

    CATEGORY_CHOICES = (
        ('rent', 'Ijara'),
        ('salary', 'Ish haqi'),
        ('utilities', 'Kommunal'),
        ('transport', 'Transport'),
        ('marketing', 'Marketing'),
        ('supplies', 'Ofis / jihozlar'),
        ('tax', 'Soliq / bojxona'),
        ('maintenance', 'Ta’mirlash'),
        ('other', 'Boshqa'),
    )

    branch = models.ForeignKey(
        Branch, on_delete=models.CASCADE, related_name='expenses', verbose_name='Filial'
    )
    category = models.CharField(
        'Kategoriya', max_length=30, choices=CATEGORY_CHOICES, default='other'
    )
    title = models.CharField('Nomi', max_length=200)
    amount = models.DecimalField('Summa', max_digits=14, decimal_places=2)
    currency = models.CharField('Valyuta', max_length=3, choices=CURRENCY_CHOICES, default=CURRENCY_UZS)
    expense_date = models.DateField('Sana', default=timezone.localdate)
    note = models.CharField('Izoh', max_length=255, blank=True)
    created_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recorded_expenses',
        verbose_name='Yozgan',
    )
    created_at = models.DateTimeField('Yaratilgan', auto_now_add=True)
    is_active = models.BooleanField('Faol', default=True)

    class Meta:
        verbose_name = 'Xarajat'
        verbose_name_plural = 'Xarajatlar'
        ordering = ['-expense_date', '-created_at']

    def __str__(self):
        return f"{self.title} — {self.amount} {self.currency}"

    def soft_delete(self):
        self.is_active = False
        self.save(update_fields=['is_active'])


class SaleReturn(models.Model):
    """Mijozdan mahsulot qaytarish (vazvrat) — pul + ombor."""

    STATUS_CHOICES = (
        ('Completed', 'Yakunlangan'),
        ('Cancelled', 'Bekor qilingan'),
    )

    order = models.ForeignKey(
        Order, on_delete=models.PROTECT, related_name='returns', verbose_name='Buyurtma',
    )
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, verbose_name='Filial')
    employee = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='processed_returns', verbose_name='Qaytargan xodim',
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='returns', verbose_name='Mijoz',
    )
    return_date = models.DateTimeField('Qaytarish sanasi', auto_now_add=True)
    total_amount = models.DecimalField('Jami summa', max_digits=14, decimal_places=2, default=Decimal('0.00'))
    cash_refunded = models.DecimalField(
        'Naqd qaytarilgan', max_digits=14, decimal_places=2, default=Decimal('0.00'),
    )
    debt_reduced = models.DecimalField(
        'Qarz kamaytirilgan', max_digits=14, decimal_places=2, default=Decimal('0.00'),
    )
    currency = models.CharField('Valyuta', max_length=3, choices=CURRENCY_CHOICES, default=CURRENCY_UZS)
    reason = models.CharField('Sabab', max_length=255, blank=True)
    status = models.CharField('Holat', max_length=20, choices=STATUS_CHOICES, default='Completed')
    receipt_number = models.CharField('Chek raqami', max_length=40, unique=True)
    is_active = models.BooleanField('Faol', default=True)

    class Meta:
        verbose_name = 'Qaytarish'
        verbose_name_plural = 'Qaytarishlar'
        ordering = ['-return_date']

    def __str__(self):
        return f"Qaytarish {self.receipt_number} — #{self.order_id}"


class SaleReturnItem(models.Model):
    sale_return = models.ForeignKey(
        SaleReturn, on_delete=models.CASCADE, related_name='items', verbose_name='Qaytarish',
    )
    order_item = models.ForeignKey(
        OrderItem, on_delete=models.PROTECT, related_name='return_items', verbose_name='Buyurtma bandi',
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name='Mahsulot')
    quantity = models.DecimalField('Miqdor', max_digits=12, decimal_places=3)
    unit_price = models.DecimalField('Birlik narxi', max_digits=14, decimal_places=2)
    line_total = models.DecimalField('Qator jami', max_digits=14, decimal_places=2)

    class Meta:
        verbose_name = 'Qaytarish bandi'
        verbose_name_plural = 'Qaytarish bandlari'

    def __str__(self):
        return f"{self.product} × {self.quantity}"


class ProductReservation(models.Model):
    STATUS_CHOICES = (
        ('Active', 'Faol'),
        ('Cancelled', 'Bekor qilingan'),
        ('Completed', 'Yakunlangan'),
    )

    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, verbose_name='Filial')
    employee = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reservations', verbose_name='Xodim',
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reservations', verbose_name='Mijoz',
    )
    customer_name = models.CharField('Mijoz nomi', max_length=150)
    phone = models.CharField('Telefon', max_length=30, blank=True)
    currency = models.CharField('Valyuta', max_length=3, choices=CURRENCY_CHOICES, default=CURRENCY_UZS)
    total_amount = models.DecimalField('Jami summa', max_digits=14, decimal_places=2, default=0)
    item_count = models.PositiveIntegerField('Mahsulot soni', default=0)
    unit_count = models.PositiveIntegerField('Jami dona', default=0)
    status = models.CharField('Holat', max_length=20, choices=STATUS_CHOICES, default='Active')
    note = models.CharField('Izoh', max_length=255, blank=True)
    stock_held = models.BooleanField('Ombordan ushlab turilgan', default=True)
    created_at = models.DateTimeField('Yaratilgan', auto_now_add=True)
    updated_at = models.DateTimeField('Yangilangan', auto_now=True)

    class Meta:
        verbose_name = 'Bron'
        verbose_name_plural = 'Bronlar'
        ordering = ['-created_at']

    def __str__(self):
        return f"Bron #{self.pk}: {self.customer_name} ({self.total_amount} {self.currency})"


class ProductReservationItem(models.Model):
    reservation = models.ForeignKey(
        ProductReservation, on_delete=models.CASCADE, related_name='items', verbose_name='Bron',
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name='Mahsulot')
    quantity = models.PositiveIntegerField('Miqdor', default=1)
    unit_price = models.DecimalField('Narx', max_digits=14, decimal_places=2)
    line_total = models.DecimalField('Qator jami', max_digits=14, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Bron qatori'
        verbose_name_plural = 'Bron qatorlari'

    def __str__(self):
        return f"{self.product} × {self.quantity}"
